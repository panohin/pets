import football_predict_config
import os
from football_data_api import data_fetchers
import json
import datetime
import mysql.connector
import telebot
from telebot import types
import pytz

bot = telebot.TeleBot(football_predict_config.token) # Ввод токена телеграм и создание объекта bot
os.environ["FOOTBALL_DATA_API"] = football_predict_config.football_data_api # ввод токена football api
db = mysql.connector.connect(
    host=football_predict_config.host,
    user=football_predict_config.user,
    password=football_predict_config.password,
    port=football_predict_config.port,
    database=football_predict_config.database)    # выбор базы данных
cursor = db.cursor()    # создание объекта cursor
data = data_fetchers.CompetitionData(competition_name=football_predict_config.compet_name) # выгузка данных о АПЛ
date_today = datetime.datetime.now()
# matches = data.get_info('matches', dateFrom = "2020-09-12", dateTo = date_today, status = 'FINISHED', matchday = 1).get('matches') # пример получения информации о матчах первого тура

present_matchday = football_predict_config.present_matchday


def convert_date(date_str):
    date = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    date = date + datetime.timedelta(hours=3)
    return date


matches = data.get_info('matches')
teams = data.get_info('teams').get('teams') # Получение списка teams в формате list
current_matchday = matches.get('matches')[0].get('season').get('currentMatchday')



user_data = {}
class User:
    def __init__(self, first_name):
        self.first_name = first_name
        self.last_name=''


#################################################################
# with open("matches.txt", "w") as file:
#    file.write(json.dumps(matches.get('matches'), indent=4))    #   C:\Users\retyu\PycharmProjects\telegram_bot
# with open("teams.txt", "w") as file:
#   file.write(json.dumps(data.get_info('teams'), indent=4))
#################################################################

# ЗАПОЛНЕНИЕ ТАБЛИЦЫ teams
# #for team in teams:
#     id = team.get('id')
#     name = team.get('name')
#     shortName = team.get('shortName')
#     sql = "INSERT INTO teams (id, name, shortName) VALUES (%s, %s, %s)"
#     val =  (id, name, shortName)
#     cursor.execute(sql,val)
#     db.commit()
#     print(id)

# Заполенение таблицы matches:
# sql = 'delete from matches'
# cursor.execute(sql)
# db.commit()
# for match in matches.get('matches'):
#     id = match.get('id')
#     date = match.get('utcDate')
#     matchday = match.get('matchday')
#     homeTeam = match.get('homeTeam').get('id')
#     awayTeam = match.get('awayTeam').get('id')
#     homeGoals = match.get('score').get('fullTime').get('homeTeam')
#     awayGoals = match.get('score').get('fullTime').get('awayTeam')
#     print([id, date, matchday, homeTeam, awayTeam, homeGoals, awayGoals])
#     sql = "INSERT INTO matches (id, date, matchday, homeTeam, awayTeam, homeGoals, awayGoals) VALUES (%s, %s, %s, %s, %s, %s, %s)"
#     val =  (id, date, matchday, homeTeam, awayTeam, homeGoals, awayGoals)
#     cursor.execute(sql,val)
#     db.commit()

######################################
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(message.chat.id, 'Нажми /start, чтобы зарегистрироваться или проверить регистрацию. Нажми /next_matchday, чтобы начать предсказывать результаты матчей АПЛ ближайшего тура. Удачи!')


@bot.message_handler(commands=['start'])
def start_command(message):
    sql = 'SELECT telegram_id FROM users WHERE telegram_id = (%s)'
    tel_id = (message.chat.id, )
    cursor.execute(sql, tel_id)
    result = cursor.fetchone()
    if result is None:
        msg = bot.send_message(message.chat.id, 'Необходимо зарегистрироваться. Введите Вашу фамилию')
        bot.register_next_step_handler(msg, register_step)
    else:
        sql = "SELECT name, lastName from users WHERE telegram_id = (%s)"
        cursor.execute(sql, tel_id)
        name_lastName = cursor.fetchall()
        bot.send_message(message.chat.id, 'Добро пожаловать, '+str(name_lastName[0][0])+' '+ str(name_lastName[0][1]))

def register_step(message):
    try:
        user_id = message.from_user.id
        user_data[user_id] = User(message.text)
        msg = bot.send_message(message.chat.id, "Ваше имя")
        bot.register_next_step_handler(msg, last_name_step)
    except Exception as e:
        bot.reply_to(message, 'Ошибка в записи фамилии')

def last_name_step(message):
    try:
        user_id = message.from_user.id
        user = user_data[user_id]
        user.last_name = message.text
        sql = "INSERT INTO users (telegram_id, lastName, name) VALUES (%s, %s, %s)"
        val = ( user_id, user.first_name, user.last_name)
        cursor.execute(sql, val)
        db.commit()
        msg = bot.send_message(message.chat.id, "Вы успешно зарегистрированы")
    except Exception as e:
        bot.reply_to(message, 'Ошибка. Может Вы уже зарегистрированы?')


@bot.message_handler(commands=['next_matchday'])
def predict_next_matchday(message):
    sql = 'SELECT matches.id, teams.homeTeam, teams.awayTeam, matches.date\
           FROM (SELECT t1.shortName as homeTeam, t2.shortName as awayTeam, t1.id as t1, t2.id as t2\
                 FROM teams t1 CROSS JOIN teams t2 \
                 WHERE t1.shortName<>t2.shortName) teams \
            JOIN (SELECT m1.date, m1.homeTeam, m2.awayTeam, m1.id \
                  FROM matches m1 JOIN matches m2 USING (id) \
                  WHERE m1.matchday = (%s)) matches \
            ON teams.t1 = matches.homeTeam and teams.t2=matches.awayTeam \
            ORDER BY date   '
    next_tour = (football_predict_config.present_matchday, )
    cursor.execute(sql, next_tour)
    result = cursor.fetchall()
    dct_of_times = []
    for match in result:
        dct_of_times.append(match[3])
    first_match_start = convert_date(min(dct_of_times))
    bot.send_message(message.chat.id, 'Начало первого матча - '+str(first_match_start.date()) +', в '+ str(first_match_start.time())+' по московскому времени.')
    for match in result:
        user_id = message.from_user.id
        match_id = match[0]
        start_match_time = convert_date(match[3])
        if datetime.datetime.now()!=start_match_time:     ### ЗАМЕНИТЬ ТУТ НА <
            bot.send_message(message.chat.id, str(match[0])+' - ' + match[1]+' - '+ match[2])
        try:
            sql = 'INSERT INTO user_predict (user_id, match_id) VALUES (%s, %s)'
            values = (user_id, match_id)
            cursor.execute(sql, values)
            db.commit()
        except mysql.connector.errors.IntegrityError:
            pass
    bot.register_next_step_handler(message, commit_step)

@bot.message_handler(commands=['rating'])
def get_rating(message):
    sql = "SELECT name, lastName, points FROM users ORDER BY points DESC"
    cursor.execute(sql)
    result = cursor.fetchall()
    for match in result:
        bot.send_message(message.chat.id, str(match[0])+' '+str(match[1])+" "+str(match[2]))

@bot.message_handler(commands=['my_prediction'])
def my_prediction(message):
    sql = "select t.homeTeam, t.awayTeam ,pred_homeGoals, pred_awayGoals\
            from user_predict up join matches m on up.match_id=m.id join (select t1.shortName as homeTeam, t2.shortName as awayTeam, t1.id as home_id, t2.id as away_id  from teams t1 cross join teams t2 on t1.id<>t2.id) t on m.homeTeam=t.home_id and m.awayTeam=t.away_id\
            where matchday=%s and user_id=%s \
            ORDER BY date"
    values = (present_matchday, message.from_user.id)
    cursor.execute(sql, values)
    result = cursor.fetchall()
    for match in result:
        bot.send_message(message.chat.id, match[0]+" - "+match[1]+" "+str(match[2])+" - "+str(match[3]))


@bot.message_handler(content_types=['text'])
def commit_step(message):
    try:
        if message.reply_to_message is not None and int((message.reply_to_message.text.split(' - '))[0])!=0:
            print(message.reply_to_message)
            try:
                bot.edit_message_text(message.reply_to_message.text +' '+ message.text,message.chat.id,message.reply_to_message.message_id)
                user_id = message.from_user.id
                match_id = int(message.reply_to_message.text.split(' - ')[0])
                # homeTeam = message.reply_to_message.text.split(' - ')[1]
                # awayTeam = message.reply_to_message.text.split(' - ')[2]
                pred_homeGoals = message.text.split('-')[0]
                pred_awayGoals = message.text.split('-')[1]
                sql = 'select id, date from matches'
                cursor.execute(sql)
                match_id_date = cursor.fetchall()
                print(match_id_date)
                for match in match_id_date:
                    if match_id==match[0]:
                        start_match_time = convert_date(match[1])
                        print(type(start_match_time))
                        print(type(date_today))
                if date_today<start_match_time: ### ЗАМЕНИТЬ ТУТ НА <
                    sql = 'UPDATE user_predict SET pred_homeGoals = %s, pred_awayGoals = %s WHERE user_id=%s and match_id=%s'
                    values = (pred_homeGoals, pred_awayGoals,  user_id, match_id)
                    try:
                        cursor.execute(sql, values)
                        db.commit()
                        print('результат записан')
                    except mysql.connector.errors.DatabaseError:
                        bot.send_message(message.chat.id, 'Ошибка. Попробуйте снова')
                else:
                    bot.send_message(message.chat.id, 'Данный матч уже стартовал. Прогноз не принимается')
            except:
                bot.send_message(message.chat.id, 'какая то ошибка')
                bot.send_message(message.chat.id,
                                 'Нажми /start, чтобы зарегистрироваться или проверить регистрацию. Нажми /next_matchday, чтобы начать предсказывать результаты матчей АПЛ ближайшего тура. Удачи!')
    except ValueError:
        bot.send_message(message.chat.id, "Указывай твой прогназ в разделе /next_matchday, отвечая на матчи!")


def calculate_points():
    sql = "SELECT  u.telegram_id as user_id, match_id, pred_homeGoals, pred_awayGoals, homeTeam, awayTeam, homeGoals, awayGoals, matchday\
            FROM users u JOIN user_predict up ON u.telegram_id=up.user_id JOIN matches m ON up.match_id=m.id where matchday<2"
    values = (football_predict_config.present_matchday+1, )
    cursor.execute(sql)
    result = cursor.fetchall()
    print(result)
    for predicted_match in result:
        user_id = predicted_match[0]
        match_id = predicted_match[1]
        pred_homeGoals = predicted_match[2]
        pred_awayGoals = predicted_match[3]
        homeTeam = predicted_match[4]
        awayTeam = predicted_match[5]
        homeGoals = predicted_match[6]
        awayGoals = predicted_match[7]
        matchday = predicted_match[8]
        point_counter = 0
        if awayGoals is not None:
            if pred_homeGoals==homeGoals and pred_awayGoals==awayGoals:
                point_counter+=4
            elif pred_homeGoals-pred_awayGoals==homeGoals-awayGoals:
                point_counter+=3
            elif (pred_homeGoals-pred_awayGoals)*(homeGoals-awayGoals)>0:
                point_counter+=2
            elif pred_homeGoals-pred_awayGoals+homeGoals-awayGoals==0 and pred_homeGoals-pred_awayGoals-homeGoals+awayGoals==0:
                point_counter+=2
            sql = 'UPDATE users SET points=points+(%s) WHERE telegram_id=(%s)'
            values = (point_counter, user_id)
            cursor.execute(sql, values)
            db.commit()
    print('очки посчитаны')

# calculate_points()


# sql = 'Delete from user_predict'
# sql = 'update users set points = 0'
# sql = 'Delete from users'

# cursor.execute(sql)
# db.commit()


bot.polling(none_stop=True)
