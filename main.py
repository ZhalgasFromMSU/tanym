import telebot
import json
import mysql.connector
import threading
import time
from telebot import types
from collections import defaultdict
from config import problem_types, TOKEN, db_user, db_password, pamyatka, conf_polit


mydb, cursor = None, None


def make_connection():
    global mydb, cursor
    mydb = mysql.connector.connect(
        host='localhost',
        user=db_user,
        password=db_password,
        database='tanym'
    )

    cursor = mydb.cursor(buffered=True)
    cursor.execute("CREATE TABLE IF NOT EXISTS psychologists ("
                   "problem_type VARCHAR(100), "
                   "client_sex INT, " #1 - муж/жен, 2 - жен, 3 - муж
                   "client_lang INT, " #1 - рус/каз, 2 - рус, 3 - каз
                   "chat_id VARCHAR(100), "
                   "name VARCHAR(100))")

    cursor.execute("CREATE TABLE IF NOT EXISTS clients ("
                   "date DATETIME, "
                   "chat_id VARCHAR(100), "
                   "name VARCHAR(100), "
                   "city VARCHAR(100), "
                   "sex INT, " #2 - жен, 3 -муж
                   "age VARCHAR(30), "
                   "type VARCHAR(100), "
                   "description VARCHAR(1000), "
                   "status INT, "
                   "review_score INT, "
                   "review VARCHAR(1000))") # status 0 sent, 1 helped

    cursor.execute("CREATE TABLE IF NOT EXISTS assignments ("
                   "client_id VARCHAR(100), "
                   "ps_chat_id VARCHAR(100), "
                   "msg_id VARCHAR(100))")


def close_connection():
    cursor.close()
    mydb.close()


clients_dict = defaultdict(dict)
doctors_dict = defaultdict(dict)


bot = None

def start_polling():
    global bot
    print("Starting bot polling")
    while True:
        try:
            print("New bot instance")
            make_connection()
            bot = telebot.TeleBot(TOKEN, threaded=False)
            botactions()
            bot.polling(none_stop=True)
        except Exception as ex:
            print("Bot polling failed. Error:\n{}".format(ex))
            close_connection()
            bot.stop_polling()
            time.sleep(30)


def botactions():
    @bot.message_handler(commands=['start'])
    def start_message(message):
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        keyboard.row("Мне нужна психологическая помощь")
        keyboard.row("Я психолог")
        bot.send_message(message.chat.id, 'Чем вам помочь?', reply_markup=keyboard)


    @bot.message_handler(func=lambda message: message.text in ("Мне нужна психологическая помощь",
                                                               "Я психолог"))
    def path_choser(message):
        if message.text.startswith("Я"):
            bot.send_message(message.chat.id, 'Введите пароль, чтобы зарегистрироваться')
            bot.register_next_step_handler(message, get_password)
        elif message.text.startswith("М"):
            cursor.execute("SELECT status FROM clients WHERE chat_id={}".format(message.chat.id))
            for status, *_ in cursor:
                if status == 1:
                    bot.send_message(message.chat.id, "Вы уже обращались в Таным. "
                                                      "В рамках проекта вы можете записаться только один раз")
                    return
            else:
                cursor.execute("DELETE FROM clients WHERE chat_id={}".format(message.chat.id))
                cursor.execute("DELETE FROM assignments WHERE client_id={}".format(message.chat.id))
                mydb.commit()
            ask_client_name(message.chat.id)


    def ask_client_name(chat_id):
        msg = bot.send_message(chat_id, "Как вас зовут?")
        bot.register_next_step_handler(msg, get_client_name)


    def get_client_name(message):
        clients_dict[message.chat.id]['name'] = message.text
        ask_client_sex(message.chat.id)


    def ask_client_sex(chat_id):
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for sex in ('Женский', 'Мужской'):
            keyboard.row(sex)
        msg = bot.send_message(chat_id, text='Ваш пол?', reply_markup=keyboard)
        bot.register_next_step_handler(msg, get_client_sex)


    def get_client_sex(message):
        clients_dict[message.chat.id]['sex'] = (3 if message.text == 'Мужской' else 2)
        ask_client_lang(message.chat.id)


    def ask_client_lang(chat_id):
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for lang in ('Русский', 'Казахский'):
            keyboard.row(lang)
        msg = bot.send_message(chat_id, text='На каком языке вам удобнее говорить?', reply_markup=keyboard)
        bot.register_next_step_handler(msg, get_client_lang)


    def get_client_lang(message):
        clients_dict[message.chat.id]['lang'] = (3 if message.text == 'Казахский' else 2)
        ask_client_age(message.chat.id)


    def ask_client_age(chat_id):
        msg = bot.send_message(chat_id, 'Ваш возраст? (напишите цифрами, например 29)')
        bot.register_next_step_handler(msg, get_client_age)


    def get_client_age(message):
        try:
            if int(message.text) < 18:
                bot.send_message(message.chat.id,
                                 text="Мы консультируем несовершеннолетних только с разрешения родителей\. "
                                 "Напишите нам в [инстаграм](https://www.instagram.com/tanymproject/)",
                                 parse_mode="MarkdownV2")
                del clients_dict[message.chat.id]
                return
        except ValueError as e:
            pass
        clients_dict[message.chat.id]['age'] = message.text
        ask_client_city(message.chat.id)


    def ask_client_city(chat_id):
        msg = bot.send_message(chat_id, 'Из какого вы города?')
        bot.register_next_step_handler(msg, get_client_city)


    def get_client_city(message):
        clients_dict[message.chat.id]['city'] = message.text
        ask_client_problem(message.chat.id)


    def ask_client_problem(chat_id):
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for problem_type in problem_types:
            keyboard.row(problem_type)
        msg = bot.send_message(chat_id,
                               text='Какая у вас проблема? Выберите из списка',
                               reply_markup=keyboard)
        bot.register_next_step_handler(msg, get_client_problem)


    def get_client_problem(message):
        clients_dict[message.chat.id]['type'] = message.text
        ask_client_pr_descr(message.chat.id)


    def ask_client_pr_descr(chat_id):
        msg = bot.send_message(chat_id, 'Опишите вашу проблему')
        bot.register_next_step_handler(msg, get_client_pr_descr)


    def get_client_pr_descr(message):
        clients_dict[message.chat.id]['description'] = message.text
        finish_client_registr(message.chat.id)


    def finish_client_registr(chat_id):
        register_client(clients_dict[chat_id], chat_id)
        if send_arrangement(clients_dict[chat_id], chat_id):
            bot.send_message(chat_id, "Вы ответили на все вопросы. "
                                      "Я напишу вам, как найду подходящего психолога")
        else:
            bot.send_message(chat_id, "К сожалению, я не нашел для вас психолога. "
                                      "Попробуйте изменить тип проблемы или язык")
        del clients_dict[chat_id]


    def register_client(client, chat_id):
        cmd = ("INSERT INTO clients "
              "(date, chat_id, name, city, sex, age, type, description, status, review) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, '')")
        vals = (time.strftime('%Y-%m-%d %H:%M:%S'),
                chat_id,
                client['name'][:98],
                client['city'][:98],
                client['sex'],
                client['age'][:28],
                client['type'][:98],
                client['description'][:998])
        cursor.execute(cmd, vals)
        mydb.commit()


    def send_arrangement(client, chat_id):
        keys = zip(
                   ('name', 'age', 'city', 'type', 'description'),
                   ('Имя', 'Возраст', 'Город', 'Тип проблемы', 'Описание'),
               )
        message_text = "\n".join("{0}: {1}".format(ru_key, client[key]) for key, ru_key in keys)
        cmd = "INSERT INTO assignments (client_id, ps_chat_id, msg_id) VALUES (%s, %s, %s)"
        vals = list()
        cursor.execute("SELECT chat_id, client_sex, client_lang FROM psychologists WHERE problem_type='{}'".format(client['type']))
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(text='Беру', callback_data='Yes'))
        keyboard.add(types.InlineKeyboardButton(text='Не беру', callback_data='No'))
        keyboard.add(types.InlineKeyboardButton(text='Статус клиента', callback_data='Status'))
        for chat, sex, lang in cursor:
            if client['sex'] % sex != 0 or client['lang'] % lang != 0:
                continue
            msg = bot.send_message(int(chat), message_text, reply_markup=keyboard)
            vals.append((chat_id, msg.chat.id, msg.message_id))
        if len(vals) == 0:
            return False
        cursor.executemany(cmd, vals)
        mydb.commit()
        return True


    @bot.callback_query_handler(func=lambda callback: callback.data in ('Yes', 'No', 'Status', 'PsHelped', 'Ignore'))
    def process_callback_psych(callback):
        if callback.data != 'Status':
            try:
                bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id)
            except Exception:
                pass
        if callback.data == 'Yes':
            cursor.execute("SELECT client_id FROM assignments WHERE ps_chat_id='{0}' AND msg_id='{1}'".format(
                    callback.message.chat.id,
                    callback.message.message_id))
            client_id = -1
            for i, *_ in cursor:
                client_id = i
            if client_id != -1:
                cursor.execute("SELECT ps_chat_id, msg_id FROM assignments WHERE client_id={}".format(client_id))
                for ps_chat, msg_id in cursor:
                    if int(ps_chat) != int(callback.message.chat.id):
                        try:
                            bot.delete_message(int(ps_chat), int(msg_id))
                        except Exception:
                            pass
                cursor.execute("DELETE FROM assignments WHERE "
                               "client_id='{0}' AND "
                               "ps_chat_id!='{1}' AND "
                               "msg_id!='{2}'".format(client_id,
                                                      callback.message.chat.id,
                                                      callback.message.message_id))
                mydb.commit()
                bot.answer_callback_query(callback_query_id=callback.id, text="Клиент теперь ваш. "
                                                                              "Скоро с вами свяжется")
                bot.send_message(int(client_id), "Психолог @{} (это ссылка, нажмите на нее) "
                                                 "согласился вам помочь".format(callback.from_user.username))
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(text='Консультация прошла', callback_data='Helped'))
                keyboard.add(types.InlineKeyboardButton(text='Отказываюсь', callback_data='Reject'))
                bot.send_message(int(client_id), pamyatka, reply_markup=keyboard)
                keyboard_ps = types.InlineKeyboardMarkup()
                keyboard_ps.add(types.InlineKeyboardButton(text='Запрос закрыт', callback_data='PsHelped'))
                keyboard_ps.add(types.InlineKeyboardButton(text='Клиент не написал', callback_data='Ignore'))
                try:
                    bot.edit_message_reply_markup(
                        chat_id=callback.message.chat.id,
                        message_id=callback.message.message_id,
                        reply_markup=keyboard_ps)
                except Exception:
                    pass
            else:
                bot.answer_callback_query(callback_query_id=callback.id, text="Занят")
        elif callback.data == "Status":
            cursor.execute(
                "SELECT client_id FROM assignments WHERE ps_chat_id={0} AND msg_id={1}".format(
                    callback.message.chat.id,
                    callback.message.message_id))
            client_id = -1
            for i, *_ in cursor:
                client_id = i
            if client_id == -1:
                ans_text = "Занят"
            else:
                ans_text = "Свободен"
            bot.answer_callback_query(callback_query_id=callback.id, text=ans_text)
        elif callback.data == "Ignore":
            cursor.execute(
                "SELECT client_id FROM assignments WHERE ps_chat_id={0} AND msg_id={1}".format(
                    callback.message.chat.id,
                    callback.message.message_id))
            for client_id, *_ in cursor.fetchall():
                cursor.execute("SELECT status FROM clients WHERE chat_id={}".format(client_id))
                for status, *_ in cursor:
                    if status == 1:
                        return
                bot.send_message(int(client_id), "Ваш запрос удалился, потому что вы не связались с "
                                                 "психологом в течение дня. Но вы можете записаться снова")
                cursor.execute("DELETE FROM assignments WHERE client_id={}".format(client_id))
                cursor.execute("DELETE FROM clients WHERE chat_id={}".format(client_id))
                mydb.commit()
                try:
                    bot.delete_message(callback.message.chat.id, callback.message.message_id)
                except Exception as err:
                    print(err)
        elif callback.data == "PsHelped":
            cursor.execute(
                "SELECT client_id FROM assignments WHERE ps_chat_id={0} AND msg_id={1}".format(
                    callback.message.chat.id,
                    callback.message.message_id))
            for client_id, *_ in cursor.fetchall():
                cursor.execute("SELECT status FROM clients WHERE chat_id={}".format(client_id))
                for status, *_ in cursor:
                    if status == 1:
                        return
                cursor.execute("UPDATE clients SET status=1 WHERE chat_id={}".format(client_id))
                mydb.commit()
                ask_client_review_score(int(client_id))
                try:
                    bot.delete_message(callback.message.chat.id, callback.message.message_id)
                except Exception as err:
                    print(err)


    @bot.callback_query_handler(func=lambda callback: callback.data in ('Reject', 'Helped'))
    def process_callback_client(callback):
        try:
            bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id)
        except Exception as exp:
            print("InException ", exp)
        client_id = callback.message.chat.id
        cursor.execute("SELECT status FROM clients WHERE chat_id={}".format(client_id))
        for status, *_ in cursor:
            if status == 1:
                return
        if callback.data == 'Helped':
            cursor.execute("UPDATE clients SET status=1 WHERE chat_id={}".format(client_id))
            mydb.commit()
            ask_client_review_score(int(client_id))
        elif callback.data == 'Reject':
            cursor.execute("SELECT ps_chat_id, msg_id FROM assignments WHERE client_id={}".format(client_id))
            for ps_chat, msg_id in cursor:
                bot.send_message(int(ps_chat),
                                 text="Этот клиент отказался от консультации",
                                 reply_to_message_id=int(msg_id))
            cursor.execute("DELETE FROM clients WHERE chat_id={}".format(client_id))
            cursor.execute("DELETE FROM assignments WHERE client_id={}".format(client_id))
            mydb.commit()
            bot.send_message(client_id, "Если вы решите обратиться снова, то введите '/start'")


    def ask_client_review_score(chat_id):
        bot.send_message(chat_id, "Не забудьте оплатить консультацию")
        msg = bot.send_message(chat_id, "По шкале от 1 до 3, оцените ваши ощущения от обращения\n"
                                        "1 - не очень, 2 - хорошо, 3 - отлично")
        bot.register_next_step_handler(msg, get_client_review_score)


    def get_client_review_score(message):
        score = 3
        try:
            score = int(message.text)
            if score not in range(1, 4):
                score = 3
        except:
            pass
        cursor.execute("UPDATE clients SET review_score={0} WHERE chat_id={1}".format(score, message.chat.id))
        mydb.commit()
        msg = bot.send_message(message.chat.id, "Оставьте, пожалуйста, отзыв. Они помогают нам развиваться")
        bot.register_next_step_handler(msg, review_review)


    def review_review(message):
        cursor.execute("UPDATE clients SET review='{}' WHERE chat_id='{}'".format(message.text[:998], message.chat.id))
        mydb.commit()
        bot.send_message(message.chat.id,
                         text="Спасибо за отзыв\! Подписывайтесь на наш [инстаграм](https://www.instagram.com/tanymproject/)",
                         parse_mode="MarkdownV2")
        sticker = message.chat.id % 4 + 1
        stick = open("stickers/end{}.webp".format(sticker), 'rb')
        bot.send_sticker(message.chat.id, stick)
        stick.close()


    def get_password(message):
        if message.text != "15092020":
            bot.send_message(message.chat.id, "Неверный пароль")
            return
        bot.send_message(message.chat.id, "Введите ФИО")
        bot.register_next_step_handler(message, get_psych_lang)


    def get_psych_lang(message):
        doctors_dict[message.chat.id]['name'] = message.text
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for lang in ("Русский", "Казахский", "Русский и казахский"):
            keyboard.row(lang)
        bot.send_message(message.chat.id, "На каком языке Вы хотите общаться с клиентами?", reply_markup=keyboard)
        bot.register_next_step_handler(message, get_fio)


    def get_fio(message):
        langs = ("Русский и казахский", "Русский", "Казахский")
        if message.text in langs:
            doctors_dict[message.chat.id]['client_lang'] = langs.index(message.text) + 1
        else:
            doctors_dict[message.chat.id]['client_lang'] = 2
        keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        for row in ("Женщины", "Мужчины", "Мужчины и женщины"):
            keyboard.row(row)
        bot.send_message(message.chat.id, "Выберите, с кем Вы работаете", reply_markup=keyboard)
        bot.register_next_step_handler(message, get_client_sexes)


    def get_client_sexes(message):
        sexes = ("Мужчины и женщины", "Женщины", "Мужчины")
        if message.text in sexes:
            doctors_dict[message.chat.id]['client_sex'] = sexes.index(message.text) + 1
        else:
            doctors_dict[message.chat.id]['client_sex'] = 1
        choose_text = ("Введите через пробел темы, в с которыми Вы работаете (например: 3 8 13), "
                      "введите 0, если не хотите ничего добавлять:\n{0}".format(
            "\n".join("{0}) {1}".format(i + 1, name) for i, name in enumerate(problem_types))))
        bot.send_message(message.chat.id, choose_text)
        bot.register_next_step_handler(message, get_expertise)


    def get_expertise(message):
        try:
            doctors_dict[message.chat.id]['expertise'] = [
                problem_types[int(i) - 1] for i in sorted(message.text.split(), key=int) if i != '0'
            ]
        except Exception as e:
            bot.send_message(message.chat.id, "Вы ввели номера неправильно, попробуйте зарегистрироваться еще раз")
            del doctors_dict[message.chat.id]
            return
        try:
            register_doctor(doctors_dict[message.chat.id], message.chat.id)
        except mysql.connector.Error as err:
            bot.send_message(message.chat.id, "База данных перегружена, попробуйте снова через некоторое время")
        del doctors_dict[message.chat.id]
        bot.send_message(message.chat.id, "Вы успешно зарегистрированы")


    def register_doctor(doctor, chat_id):
        doctor_problems = set()
        if -1 not in doctor['expertise']:
            cursor.execute("SELECT problem_type FROM psychologists WHERE chat_id={}".format(chat_id))
            for pr_type, *_ in cursor:
                doctor_problems.add(pr_type)
            cmd = ("INSERT INTO psychologists "
                   "(problem_type, client_sex, client_lang, chat_id, name) "
                   "VALUES(%s, %s, %s, %s, %s)")
            vals = [
                (pr_type, doctor['client_sex'], doctor['client_lang'], chat_id, doctor['name'])
                    for pr_type in doctor['expertise'] if pr_type not in doctor_problems
            ]
            cursor.executemany(cmd, vals)
        cursor.execute("UPDATE psychologists SET client_sex={0}, client_lang={1} "
                       "WHERE chat_id={2}".format(doctor['client_sex'], doctor['client_lang'], chat_id))
        mydb.commit()


polling_thread = threading.Thread(target=start_polling)
polling_thread.daemon = True
polling_thread.start()


if __name__ == "__main__":
    while True:
        try:
            time.sleep(120)
        except KeyboardInterrupt:
            cursor.close()
            mydb.close()
            break
