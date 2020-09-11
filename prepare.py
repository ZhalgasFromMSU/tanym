import mysql.connector
from config import db_user, db_password


mydb = mysql.connector.connect(
    host='localhost',
    user=db_user,
    password=db_password
)

cursor = mydb.cursor()
cursor.execute("CREATE DATABASE IF NOT EXISTS tanym")

cursor.close()
mydb.close()
