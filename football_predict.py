#!/usr/bin/python3.3

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

def convert_date(date_str):
    date = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    date = date + datetime.timedelta(hours=3)
    return date


matches = data.get_info('matches')
teams = data.get_info('teams').get('teams') # Получение списка teams в формате list
#present_matchday=15
present_matchday = matches.get('matches')[0].get('season').get('currentMatchday')
print(str(present_matchday)+' is present_matchday')



user_data = {}
class User:
    def __init__(self, first_name):
        self.first_name = first_name
        self.last_name=''


@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(message.chat.id,
                     '''
/start - зарегистрироваться или проверить регистрацию.
/predict - предсказать результаты матчей АПЛ ближайшего тура.
/my_prediction - уточнить свой прогноз.
/rating - общий рейтинг участников.
/help - вызов справки
Удачи!

                    '''
                     )


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
        bot.send_message(message.chat.id, 'Добро пожаловать, '+str(name_lastName[0][0])+' '+ str(name_lastName[0][1])+" /help")

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
        msg = bot.send_message(message.chat.id, "Вы успешно зарегистрированы\n/help")
    except Exception as e:
        bot.reply_to(message, 'Ошибка. Может Вы уже зарегистрированы?')

### ОБНОВЛЕНИЕ СПИСКА МАТЧЕЙ
@bot.message_handler(commands=['update'])
def start_of_matchday(message):
    #  Выгрузка в базу ближайшего (present_matchday) тура
    pres_matchday = matches.get('matches')[0].get('season').get('currentMatchday')
    bot.send_message(message.chat.id, pres_matchday)
    if message.from_user.id == football_predict_config.admin:
        for match in matches.get('matches'):
            if match['matchday'] == present_matchday:
                print(match)
                id = match.get('id')
                date = match.get('utcDate')
                matchday = present_matchday
                homeTeam = match.get('homeTeam').get('id')
                awayTeam = match.get('awayTeam').get('id')
                homeGoals = match.get('score').get('fullTime').get('homeTeam')
                awayGoals = match.get('score').get('fullTime').get('awayTeam')
                sql = "UPDATE matches SET date=%s, homeTeam=%s, awayTeam=%s, homeGoals=%s, awayGoals=%s WHERE id=%s"
                val = (date, homeTeam, awayTeam, homeGoals, awayGoals, id)
                cursor.execute(sql, val)
                db.commit()
        bot.send_message(message.chat.id, "Записано, проверяй")
       ### Выгружаем из базы список матчей тура:
    sql = 'SELECT matches.id, teams.homeTeam, teams.awayTeam, matches.date\
               FROM (SELECT t1.shortName as homeTeam, t2.shortName as awayTeam, t1.id as t1, t2.id as t2\
                     FROM teams t1 CROSS JOIN teams t2 \
                     WHERE t1.shortName<>t2.shortName) teams \
                JOIN (SELECT m1.date, m1.homeTeam, m2.awayTeam, m1.id \
                      FROM matches m1 JOIN matches m2 USING (id) \
                      WHERE m1.matchday = (%s)) matches \
                ON teams.t1 = matches.homeTeam and teams.t2=matches.awayTeam \
                ORDER BY date'
    next_tour = (present_matchday,)
    cursor.execute(sql, next_tour)
    result = cursor.fetchall()
    for match in result:
        bot.send_message(message.chat.id, match[1] + ' - ' + match[2])
    admin_keyboard = types.InlineKeyboardMarkup()
    button_yes = types.InlineKeyboardButton(text='Да!', callback_data='start_of_matchday_yes')
    admin_keyboard.add(button_yes)
    bot.send_message(message.chat.id, "OK?" , reply_markup=admin_keyboard)

@bot.message_handler(commands=['predict'])
def predict_next_matchday(message):
    sql = 'SELECT matches.id, teams.homeTeam, teams.awayTeam, matches.date\
           FROM (SELECT t1.shortName as homeTeam, t2.shortName as awayTeam, t1.id as t1, t2.id as t2\
                 FROM teams t1 CROSS JOIN teams t2 \
                 WHERE t1.shortName<>t2.shortName) teams \
            JOIN (SELECT m1.date, m1.homeTeam, m2.awayTeam, m1.id \
                  FROM matches m1 JOIN matches m2 USING (id) \
                  WHERE m1.matchday = (%s)) matches \
            ON teams.t1 = matches.homeTeam and teams.t2=matches.awayTeam \
            ORDER BY date'
    next_tour = (present_matchday, )
    cursor.execute(sql, next_tour)
    result = cursor.fetchall()
    dct_of_times = []
    for match in result:
        dct_of_times.append(match[3])
    first_match_start = convert_date(min(dct_of_times))
    bot.send_message(message.chat.id,
                     '*Матчи* ' + str(present_matchday)+ '* тура. Начало первого матча - *'+str(first_match_start.date()) +'*, в *'+ str(first_match_start.time())+'* по московскому времени.*',
                     parse_mode='Markdown')
    for match in result:
        user_id = message.from_user.id
        match_id = match[0]
        start_match_time = convert_date(match[3])
        if datetime.datetime.now()<start_match_time:     ### ЗАМЕНИТЬ ТУТ НА <
            # bot.send_message(message.chat.id, str(match[0])+' - ' + match[1]+' - '+ match[2])
            bot.send_message(message.chat.id, match[1] + ' - ' + match[2])
            if 'Leicester City' in match:
                try:
                    sql_matches = 'INSERT INTO matches (id, matchday) VALUES (%s, %s)'
                    values_matches = (present_matchday, present_matchday)
                    cursor.execute(sql_matches, values_matches)
                    db.commit()
                except mysql.connector.errors.IntegrityError:
                    pass
                vardy_keyboard = types.InlineKeyboardMarkup()
                button_yes = types.InlineKeyboardButton(text='Да!', callback_data='yes')
                button_no = types.InlineKeyboardButton(text='Нет', callback_data='no')
                vardy_keyboard.add(button_yes, button_no)
                bot.send_message(message.chat.id, "Забьёт ли Джейми Варди в этом туре?", reply_markup=vardy_keyboard)
                sql = 'INSERT INTO user_predict (user_id, match_id) VALUES (%s, %s)'
                vardy_match_id = present_matchday
                values = (user_id, vardy_match_id)
                try:
                    cursor.execute(sql, values)
                    db.commit()
                except mysql.connector.errors.IntegrityError:
                    pass
        try:
            sql_user_predict = 'INSERT INTO user_predict (user_id, match_id) VALUES (%s, %s)'
            values_user_predict = (user_id, match_id)
            cursor.execute(sql_user_predict, values_user_predict)
            db.commit()
        except mysql.connector.errors.IntegrityError:
            pass
    bot.register_next_step_handler(message, commit_step)


### ПЕРЕД ПОДСЧЁТОМ РЕЗУЛЬТАТОВ МАТЧЕЙ
@bot.message_handler(commands=['vardy_goal'])
def vardy_goal(message):
    vardy_keyboard = types.InlineKeyboardMarkup()
    button_yes = types.InlineKeyboardButton(text='Да', callback_data='goal')
    button_no = types.InlineKeyboardButton(text='Нет', callback_data='no_goal')
    vardy_keyboard.add(button_yes, button_no)
    bot.send_message(message.chat.id, "Забил Джейми Варди в" + str(present_matchday)+ " туре?", reply_markup=vardy_keyboard)
@bot.message_handler(commands=['calculate'])
def calculate_points(message):
    if message.from_user.id == football_predict_config.admin:
        sql_calculate = 'select user_id, match_id, matchday, pred_homeGoals, pred_awaygoals, homeTeamShortName, awayTeamShortName, homeGoals, awayGoals\
                        from users u left join user_predict up on u.telegram_id=up.user_id right join matches m on m.id=up.match_id left join team_names tn on m.homeTeam=tn.home_id and m.awayTeam=tn.away_id\
                        where matchday = %s'
        values = (present_matchday, )
        cursor.execute(sql_calculate, values)
        result = cursor.fetchall()
        dct_of_points = {}
        for match in result:
            user_id = match[0]
            match_id = match[1]
            pred_homeGoals = match[3]
            pred_awayGoals = match[4]
            homeTeam = match[5]
            awayTeam = match[6]
            homeGoals = match[7]
            awayGoals = match[8]
            if user_id not in dct_of_points.keys():
                dct_of_points[user_id]=0
            point_counter = 0
            if awayGoals is not None:
                if pred_homeGoals is not None:
                    if len(str(match_id)) < 3:
                        if pred_homeGoals == 1 and homeGoals == 1:
                            dct_of_points[user_id] += 4
                            point_counter += 4
                            bot.send_message(user_id, 'Угадал, что Варди забил. + 4️⃣балла')
                        elif pred_homeGoals == 0 and homeGoals == 0:
                            dct_of_points[user_id] += 3
                            point_counter += 3
                            bot.send_message(user_id, 'Угадал, что Варди не забил. + 3️балла')
                        else:
                            bot.send_message(user_id, 'Варди не принёс тебе баллов - 0️⃣')
                    elif pred_homeGoals == homeGoals and pred_awayGoals == awayGoals:
                        dct_of_points[user_id] += 4
                        point_counter += 4
                        bot.send_message(user_id, homeTeam+' - '+awayTeam+'\nСчёт: '+str(homeGoals)+' : '+str(awayGoals)+' Прогноз: '+str(pred_homeGoals)+' : '+str(pred_awayGoals)+ ' + 4️⃣балла')
                    elif pred_homeGoals - pred_awayGoals == homeGoals - awayGoals:
                        dct_of_points[user_id] += 3
                        point_counter += 3
                        bot.send_message(user_id, homeTeam+' - '+awayTeam+'\nСчёт: '+str(homeGoals)+' : '+str(awayGoals)+' Прогноз: '+str(pred_homeGoals)+' : '+str(pred_awayGoals)+ ' + 3️⃣балла')
                    elif (pred_homeGoals - pred_awayGoals) * (homeGoals - awayGoals) > 0:
                        dct_of_points[user_id] += 2
                        point_counter += 2
                        bot.send_message(user_id, homeTeam+' - '+awayTeam+'\nСчёт: '+str(homeGoals)+' : '+str(awayGoals)+' Прогноз: '+str(pred_homeGoals)+' : '+str(pred_awayGoals)+ ' + 2️⃣балла')
                    # elif pred_homeGoals - pred_awayGoals + homeGoals - awayGoals == 0 and pred_homeGoals - pred_awayGoals - homeGoals + awayGoals == 0:
                    #     point_counter += 2
                    #     bot.send_message(user_id, homeTeam+' '+awayTeam+'\nСчёт: '+str(homeGoals)+' : '+str(awayGoals)+' Прогноз: '+str(pred_homeGoals)+' : '+str(pred_awayGoals)+ '2️⃣балла')
                    else:
                        bot.send_message(user_id, homeTeam + ' - ' + awayTeam + '\nСчёт: ' + str(homeGoals) + ' : ' + str(awayGoals) + ' Прогноз: ' + str(pred_homeGoals) + ' : ' + str(pred_awayGoals) + ' 0️⃣баллов')
                else:
                    bot.send_message(user_id, homeTeam + ' - ' + awayTeam + '\nСчёт: ' + str(homeGoals) + ' : ' + str(
                        awayGoals) + ' Прогноз: ------- 0️⃣баллов')
        for user in dct_of_points:
            bot.send_message(user, 'Итог: '+ str(dct_of_points[user]))
            sql = 'UPDATE users SET points=points + %s WHERE telegram_id=%s'
            values = (dct_of_points[user], user)
            cursor.execute(sql, values)
            db.commit()

@bot.callback_query_handler(func=lambda call: True)
def call(call):
    if call.data=='yes':
        sql = 'UPDATE user_predict SET pred_homeGoals = %s, pred_awayGoals = %s WHERE user_id=%s and match_id=%s'
        values = (1, 1, call.from_user.id, present_matchday)
        bot.edit_message_text(message_id=call.message.message_id, text=call.message.text + ' ⚽ Да! ⚽', chat_id=call.message.chat.id)
        cursor.execute(sql, values)
        db.commit()
    if call.data=='no':
        sql = 'UPDATE user_predict SET pred_homeGoals = %s, pred_awayGoals = %s WHERE user_id=%s and match_id=%s'
        values = (0,0, call.from_user.id, present_matchday)
        bot.edit_message_text(message_id=call.message.message_id, text=call.message.text + ' 🙅 Нет! 🙅', chat_id=call.message.chat.id)
        cursor.execute(sql, values)
        db.commit()
    if call.data=='start_of_matchday_yes':
        sql = "SELECT telegram_id, name, lastName FROM users"
        cursor.execute(sql)
        result = cursor.fetchall()
        for match in result:
            bot.send_message(match[0], "Здравствуйте, " + str(match[1]) + " " + str(match[2]) + "! Впереди новый тур АПЛ!\n Нажимайте /predict, чтобы оставить свой прогноз!")
    if call.data=='goal':
        sql = 'UPDATE matches SET homeGoals = %s, awayGoals = %s WHERE id=%s'
        values = (1,1, present_matchday)
        cursor.execute(sql, values)
        db.commit()
    if call.data=='no_goal':
        sql = 'UPDATE matches SET homeGoals = %s, awayGoals = %s WHERE id=%s'
        values = (0,0, present_matchday)
        cursor.execute(sql, values)
        db.commit()

@bot.message_handler(commands=['rating'])
def get_rating(message):
    sql = "SELECT name, lastName, points FROM users ORDER BY points DESC"
    cursor.execute(sql)
    result = cursor.fetchall()
    for match in result:
        bot.send_message(message.chat.id, str(match[0])+' '+str(match[1])+" "+str(match[2]))

@bot.message_handler(commands=['my_prediction'])
def my_prediction(message):
    sql = "SELECT user_id, matchday, match_id, m.date, homeTeamShortName as homeTeam, awayTeamShortName as awayTeam, homeGoals, awayGoals, pred_homeGoals, pred_awayGoals \
            FROM (SELECT * FROM matches WHERE matchday=%s) m LEFT JOIN user_predict up ON m.id=up.match_id LEFT JOIN team_names tn ON m.homeTeam=tn.home_id AND m.awayTeam=tn.away_id \
            WHERE user_id=%s \
            ORDER BY date;"
    values = (present_matchday, message.from_user.id)
    cursor.execute(sql, values)
    result = cursor.fetchall()
    print(result)
    for match in result:
        if match[3] is not None:
            bot.send_message(message.chat.id, match[4]+" - "+match[5]+" "+str(match[8])+" - "+str(match[9]))
        else:
            if match[8]==1:
                bot.send_message(message.chat.id, 'Джейми Варди забьёт гол в этом туре!')
            if match[8]==0:
                bot.send_message(message.chat.id, 'Джейми Варди не забьёт в этом туре!')

@bot.message_handler(content_types=['text'])
def commit_step(message):
    try:
    # if message.reply_to_message is not None and int((message.reply_to_message.text.split(' - '))[0])!=0:
        if message.reply_to_message is not None:
            # print(message.text)
            # if message.text.split('-')[0] is not int or message.text.split('-')[1] is not int:
            #     bot.send_message(message.chat.id, "Неправильный ввод!")
            try:
                user_id = message.from_user.id
                sql_to_know_match_id = "SELECT m.id AS match_id, homeTeamShortName AS homeTeam, awayTeamShortName AS awayTeam, m.date, matchday \
                                        FROM matches m JOIN team_names tn ON m.homeTeam=tn.home_id AND m.awayTeam=tn.away_id WHERE matchday=%s;"
                values = (present_matchday, )
                cursor.execute(sql_to_know_match_id, values)
                list_to_know_match_id = cursor.fetchall()
                answered_message = message.reply_to_message.text
                homeTeam = answered_message.split(' - ')[0]
                awayTeam = answered_message.split(' - ')[1]
                try:
                    awayTeam=(answered_message.split(' - ')[1]).split(' || ')[0]
                except:
                    print('не вышло((')
                pred_homeGoals = message.text.split('-')[0]
                pred_awayGoals = message.text.split('-')[1]
                print(int(pred_homeGoals),int(pred_awayGoals))
                print(homeTeam, awayTeam, pred_homeGoals, pred_awayGoals)
                for match in list_to_know_match_id:
                    if homeTeam==match[1] and awayTeam==match[2]:
                        match_id = match[0]
                        start_match_time = match[3]
                        break
                if date_today<convert_date(start_match_time): ### ЗАМЕНИТЬ ТУТ НА <
                    sql = 'UPDATE user_predict SET pred_homeGoals = %s, pred_awayGoals = %s WHERE user_id=%s and match_id=%s'
                    values = (pred_homeGoals, pred_awayGoals,  user_id, match_id)
                    try:
                        cursor.execute(sql, values)
                        db.commit()
                        bot.edit_message_text(text=homeTeam + ' - ' + awayTeam + ' || ' + message.text,
                                              chat_id=message.chat.id, message_id=message.reply_to_message.message_id)

                    except mysql.connector.errors.DatabaseError:
                        bot.send_message(message.chat.id, 'Ошибка. Попробуйте снова')
                else:
                    bot.send_message(message.chat.id, 'Данный матч уже стартовал. Прогноз не принимается')
            except IndexError:
                bot.send_message(message.chat.id, 'Для указания счёта в режиме /predict отвечай на сообщение с матчем и вводи счёт в формате "2-1"')
    except ValueError:
        bot.send_message(message.chat.id,
                         'Для указания счёта в режиме /predict отвечай на сообщение с матчем и вводи счёт в формате "3-1"')
    bot.delete_message(message.chat.id, message.message_id)

print('OK!')
#exit()

# sql = 'Delete from user_predict'
# sql = 'update users set points = 0'
# sql = 'Delete from users'

# cursor.execute(sql)
# db.commit()
# print('OK')

try:
	bot.polling(none_stop=True)
except:
	pass



###################

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
# Заполенение таблицы matches с удалением:
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