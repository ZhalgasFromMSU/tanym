import telebot
import json
import mysql.connector
from telebot import types
from collections import defaultdict
from config import problem_types, TOKEN, db_user, db_password, pamyatka

#TODO clients_dict и doctors_dict будут жрать память, пока не закончится регистрация
#TODO предупреждать клиента, если врача не нашли, попросить поменять параметры
#TODO разбить все get функции на ask и save

mydb = mysql.connector.connect(
    host='localhost',
    user=db_user,
    password=db_password,
    database='tanym'
)


cursor = mydb.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS psychologists ("
               "problem_type VARCHAR(100), "
               "client_sex INT, " #1 - муж/жен, 2 - жен, 3 - муж
               "client_lang INT, " #1 - рус/каз, 2 - рус, 3 - каз
               "chat_id VARCHAR(100), "
               "name VARCHAR(100))")

cursor.execute("CREATE TABLE IF NOT EXISTS clients ("
               "chat_id VARCHAR(100), "
               "city VARCHAR(100), "
               "sex INT, " #2 - жен, 3 -муж
               "age VARCHAR(30), "
               "type VARCHAR(100), "
               "description VARCHAR(300), "
               "status INT, "
               "review VARCHAR(500))") # status 0 sent, 1 helped

cursor.execute("CREATE TABLE IF NOT EXISTS assignments ("
               "client_id VARCHAR(100), "
               "ps_chat_id VARCHAR(100), "
               "msg_id VARCHAR(100))")


clients_dict = defaultdict(dict)
doctors_dict = defaultdict(dict)


bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=['start'])
def start_message(message):
    keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    keyboard.row("Мне нужна психологическая помощь")
    keyboard.row("Я психолог")
    bot.send_message(message.chat.id, 'Чем вам помочь?', reply_markup=keyboard)


@bot.message_handler(func=lambda message: message.text in ("Мне нужна психологическая помощь", "Я психолог"))
def path_choser(message):
    if not message.text.startswith("Мне"):
        bot.send_message(message.chat.id, 'Введите пароль, чтобы зарегистрироваться')
        bot.register_next_step_handler(message, get_password)
    else:
        bot.send_message(message.chat.id, 'Как к вам обращаться')
        bot.register_next_step_handler(message, get_name)


def get_name(message):
    clients_dict[message.chat.id]['name'] = message.text
    keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for sex in ('Женский', 'Мужской'):
        keyboard.row(sex)
    bot.send_message(message.chat.id, text='Ваш пол?', reply_markup=keyboard)
    bot.register_next_step_handler(message, get_sex)


def get_sex(message):
    clients_dict[message.chat.id]['sex'] = (3 if message.text == 'Мужской' else 2)
    keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for lang in ('Русский', 'Казахский'):
        keyboard.row(lang)
    bot.send_message(message.chat.id, text='Какой вы предпочитаете язык общения?', reply_markup=keyboard)
    bot.register_next_step_handler(message, get_lang)


def get_lang(message):    
    clients_dict[message.chat.id]['lang'] = (3 if message.text == 'Казахский' else 2)
    bot.send_message(message.chat.id, 'Какой у вас возраст? (Число цифрами, например 29)')
    bot.register_next_step_handler(message, get_age)


def get_age(message):
    try:
        if int(message.text) < 18:
            bot.send_message(message.chat.id, "Если вам нет 18, напишите нам в Instagram")
            del clients_dict[message.chat.id]
            return
    except ValueError as e:
        pass
    clients_dict[message.chat.id]['age'] = message.text
    bot.send_message(message.chat.id, 'Из какого вы города?')
    bot.register_next_step_handler(message, get_city)


def get_city(message):
    clients_dict[message.chat.id]['city'] = message.text
    keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for problem_type in problem_types:
        keyboard.row(problem_type)
    bot.send_message(message.chat.id,
                     text='Какая у вас проблема? Нажмите на ячейку из списка',
                     reply_markup=keyboard)
    bot.register_next_step_handler(message, get_problem_type)


def get_problem_type(message):
    clients_dict[message.chat.id]['type'] = message.text
    bot.send_message(message.chat.id, 'Опишите вашу проблему')
    bot.register_next_step_handler(message, get_problem_description)


def get_problem_description(message):
    clients_dict[message.chat.id]['description'] = message.text
    register_client(clients_dict[message.chat.id], message.chat.id)
    if send_arrangement(clients_dict[message.chat.id], message.chat.id):
        bot.send_message(message.chat.id, 'Я отправил сообщение психологам. '
                                          'Напишу вам, как кто-нибудь откликнется')
    else:
        bot.send_message(message.chat.id, 'К сожалению для вас не нашлось психолога. '
                                          'Попробуйте поменять тип проблемы или язык общения')
    del clients_dict[message.chat.id]


def register_client(client, chat_id):
    cmd = ("INSERT INTO clients "
          "(chat_id, city, sex, age, type, description, status, review) "
          "VALUES (%s, %s, %s, %s, %s, %s, 0, '')")
    vals = (chat_id,
            client['city'][:98],
            client['sex'],
            client['age'][:28],
            client['type'][:98],
            client['description'][:298])
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


@bot.callback_query_handler(func=lambda callback: callback.data in ('Yes', 'No', 'Helped'))
def process_callback(callback):
    if callback.data == 'Yes':
        cursor.execute("SELECT client_id FROM assignments WHERE ps_chat_id='{0}' AND msg_id='{1}'".format(
                callback.message.chat.id,
                callback.message.message_id))
        client_id = -1
        for i, *_ in cursor:
            client_id = i
        if client_id != -1:
            cursor.execute("DELETE FROM assignments WHERE "
                           "client_id='{0}' AND "
                           "ps_chat_id!='{1}' AND "
                           "msg_id!='{2}'".format(client_id,
                                                  callback.message.chat.id,
                                                  callback.message.message_id))
            mydb.commit()
            bot.send_message(callback.from_user.id, "Клиент теперь ваш. "
                                                    "Скоро с вами свяжется")
            bot.send_message(int(client_id), "Психолог @{} (это ссылка, нажмите на нее) согласился вам помочь. "
                                             "Свяжитесь как можно скорее".format(callback.from_user.username))
            bot.send_message(int(client_id), pamyatka)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton(text='Помогли', callback_data='Helped'))
            bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=keyboard
            )
        else:
            bot.send_message(callback.from_user.id, "Клиента уже взяли")
            bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id
            )
    elif callback.data == 'No':
        bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id
        )
    else: #Helped
        bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        cursor.execute(
            "SELECT client_id FROM assignments WHERE ps_chat_id='{0}' AND msg_id='{1}'".format(
                callback.message.chat.id,
                callback.message.message_id))
        client_id = -1
        for i, *_ in cursor:
            client_id = i
        if client_id != -1:
            cursor.execute("UPDATE clients SET status=1 WHERE chat_id='{}'".format(client_id))
            mydb.commit()
            msg = bot.send_message(int(client_id), "Оставьте, пожалуйста, отзыв")
            bot.register_next_step_handler(msg, review_review)


def review_review(message):
    cursor.execute("UPDATE clients SET review='{}' WHERE chat_id='{}'".format(message.text[:498], message.chat.id))
    mydb.commit()
    bot.send_message(message.chat.id, "Спасибо за отзыв! Не забудьте оплатить консультацию")


def get_password(message):
    if message.text != "15092020":
        bot.send_message(message.chat.id, "Неверный пароль")
        return
    bot.send_message(message.chat.id, "Введите ФИО")
    bot.register_next_step_handler(message, get_lang)


def get_lang(message):
    doctors_dict[message.chat.id]['name'] = message.text
    keyboard = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for lang in ("Русский", "Казахский", "Русский и казахский"):
        keyboard.row(lang)
    bot.send_message(message.chat.id, "На каком языке вы хотите общаться с клиентами?", reply_markup=keyboard)
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
    bot.send_message(message.chat.id, "Выберите, с кем вы работаете", reply_markup=keyboard)
    bot.register_next_step_handler(message, get_client_sexes)


def get_client_sexes(message):
    sexes = ("Мужчины и женщины", "Женщины", "Мужчины")
    if message.text in sexes:
        doctors_dict[message.chat.id]['client_sex'] = sexes.index(message.text) + 1
    else:
        doctors_dict[message.chat.id]['client_sex'] = 1
    choose_text = "Введите через пробел области, в которых Вы работаете (например: 3 8 13), введите 0, если не хотите ничего добавлять:\n{0}".format(
        "\n".join("{0}) {1}".format(i + 1, name) for i, name in enumerate(problem_types)))
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
    register_doctor(doctors_dict[message.chat.id], message.chat.id)
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


bot.polling()
