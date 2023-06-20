import threading
import schedule
from mysql.connector import Error
from bs4 import BeautifulSoup
import requests
import mysql.connector
import configparser
import datetime
import telebot
import time


def get_timedelta(date):
    return ((datetime.datetime.now() -
             datetime.datetime.strptime(
                 datetime.datetime.now().strftime("%Y/%m/%d") + ', ' + date,
                 "%Y/%m/%d, %H:%M:%S")
             ).total_seconds()) < 15*60


def get_car_list(price_from, price_to, year_from, year_to):
    car_list = []

    # OLX
    olx_url = 'https://www.olx.ua/transport/legkovye-avtomobili/q-'
    olx_params = {'currency': 'USD',
                  'search[order]': 'created_at:desc',
                  'search[filter_float_price:from]': price_from,
                  'search[filter_float_price:to]': price_to,
                  'search[filter_float_motor_year:from]': year_from,
                  'search[filter_float_motor_year:to]': year_to}
    olx_response = requests.get(olx_url, params=olx_params)

    if olx_response.status_code == 200:
        olx_soup = BeautifulSoup(olx_response.content, 'html.parser')
        olx_cars = olx_soup.find_all('div', class_='offer-wrapper')

        for car in olx_cars:
            t = car.find_all('small', class_='breadcrumb x-normal')[2].find('span').text.strip()
            if not t.startswith('Сегодня') or not get_timedelta(t[8:]+':00'):
                continue
            car_info = {'title': car.find('strong').text.strip(),
                        'price': car.find('p', class_='price').text.strip(),
                        'link': car.find('a', class_='marginright5').get('href'),
                        'img': car.find('img').get('src'),
                        'date': t[8:]+':00'}
            car_list.append(car_info)

    # Auto.ria
    auto_url = 'https://auto.ria.com/search/?'
    auto_params = {'price.currency': '1',
                   'abroad.not': '0',
                   'custom.not': '1',
                   'size': '10',
                   'year[0].gte': year_from,
                   'year[0].lte': year_to,
                   'price.USD.gte': price_from,
                   'price.USD.lte': price_to,
                   'sort[0].order': 'dates.created.desc'}
    auto_response = requests.get(auto_url, params=auto_params)

    if auto_response.status_code == 200:
        auto_soup = BeautifulSoup(auto_response.content, 'html.parser')
        # print(auto_soup)
        auto_cars = auto_soup.find_all('section', class_='ticket-item')

        for car in auto_cars:
            i = car.find('div', class_='content-bar').find('source')
            t = car.find('div', class_='footer_ticket').find('span').get('data-add-date')[11:]
            if not get_timedelta(t):
                continue
            car_info = {'title': car.find('div', class_='content-bar').find_all('a')[1].get('title'),
                        'price': car.find('div', class_='price-ticket').get('data-main-price') + " $",
                        'link': car.find('div', class_='content-bar').find_all('a')[1].get('href'),
                        'img': i.get('srcset') if i is not None else None,
                        'date': t}
            car_list.append(car_info)

    return car_list


class Database:
    def __init__(self, host_name, user_name, user_password, db_name):
        self.cursor = None
        self.connect = None
        try:
            self.connect = mysql.connector.connect(
                host=host_name,
                user=user_name,
                passwd=user_password,
                database=db_name
            )
            self.cursor = self.connect.cursor()
            print("Connection to MySQL DB successful")
        except Error as e:
            print(e)

    def execute_query(self, query):
        try:
            self.cursor.execute(query)
            self.connect.commit()
            print("Query executed successfully")
        except Error as e:
            print(e)

    def insert_data(self, user_id, price_from, price_to, year_from, year_to):
        create_users = f"""
            INSERT INTO
              `users` (`user_id`, `price_from`, `price_to`, `year_from`, `year_to`)
            VALUES
              ({user_id}, {price_from}, {price_to}, {year_from}, {year_to});
            """

        self.execute_query(create_users)

    def read_data(self, user_id):
        try:
            query = f"SELECT * FROM users WHERE user_id = {user_id}"
            self.cursor.execute(query)
            result = self.cursor.fetchall()
            return result
        except Error as e:
            print(e)

    def read_all_data(self):
        try:
            query = f"SELECT * FROM users"
            self.cursor.execute(query)
            result = self.cursor.fetchall()
            return result
        except Error as e:
            print(e)

    def update_data(self, user_id, price_from, price_to, year_from, year_to):
        update_post_description = f"""
        UPDATE users
        SET price_from = {price_from}, price_to = {price_to}, year_from = {year_from}, year_to = {year_to}
        WHERE user_id = {user_id}
        """
        self.execute_query(update_post_description)


if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read('config.ini')
    username = config.get('admin', 'username')
    password = config.get('admin', 'password')
    token = config.get('admin', 'token')
    db = Database("localhost", username, password, "car_check_user_data")

    bot = telebot.TeleBot(token)

    def send_messages():
        print('Sending messages to users...')
        for i in db.read_all_data():
            _, user_id, *data = i
            print(user_id, data)
            car_list = get_car_list(*data)
            for car in car_list:
                bot.send_message(user_id, f"Название: {car['title']} \n Цена: {car['price']} \n Ссылка: {car['link']}")

    @bot.message_handler(commands=['start'])
    def start(message):
        if db.read_data(int(message.chat.id)):
            bot.send_message(message.chat.id, "Привет, все данные которые вы ввели сохранены "
                                              "вам не нужно заново вводить данные")
        else:
            bot.send_message(message.chat.id,
                             "Привет, для изменения года выпуска или цены, напишите /setparams")

    @bot.message_handler(commands=['setparams'])
    def set_params(message):
        msg = bot.send_message(message.chat.id,
                               "Напишите с года выпуска автомобилей (Пример: 2001-2017)")
        bot.register_next_step_handler(msg, set_years)

    def set_years(message):
        global year_from
        global year_to
        try:
            year_from, year_to = int(message.text.split("-")[0]), int(message.text.split("-")[1])
            if 2030 < year_from or year_from < 1900 or 1900 > year_to or year_to > 2030 or year_from > year_to:
                raise TypeError('invalid years')
        except (IndexError, ValueError):
            msg = bot.send_message(message.chat.id, "Данные неправильно введены, попробуйте еще раз")
            bot.register_next_step_handler(msg, set_years)
        except TypeError:
            msg = bot.send_message(message.chat.id, "Введите реальные года, попробуйте еще раз")
            bot.register_next_step_handler(msg, set_years)
        else:
            msg = bot.send_message(message.chat.id, "Теперь введите цену (Например 2500-7000)")
            bot.register_next_step_handler(msg, set_price)

    def set_price(message):
        try:
            price_from, price_to = int(message.text.split("-")[0]), int(message.text.split("-")[1])
            if 1000000 < price_from or price_from < 0 or 0 > price_to or price_to > 1000000 or price_from > price_to:
                raise TypeError('invalid years')
        except IndexError:
            msg = bot.send_message(message.chat.id, "Данные неправильно введены, попробуйте еще раз")
            bot.register_next_step_handler(msg, set_price)
        except TypeError:
            msg = bot.send_message(message.chat.id, "Введите реальную цену, попробуйте еще раз")
            bot.register_next_step_handler(msg, set_price)
        else:
            bot.send_message(message.chat.id, "Ваши данные записаны")
            if db.read_data(int(message.chat.id)):
                db.update_data(int(message.chat.id), price_from, price_to, year_from, year_to)
                print('Data updated:', db.read_data(int(message.chat.id)))
            else:
                db.insert_data(int(message.chat.id), price_from, price_to, year_from, year_to)
                print('New user:', db.read_data(int(message.chat.id)))


    @bot.message_handler(commands=['messages'])
    def timer(message):
        if message.chat.id == 1024318992:
            schedule.every(15).minutes.do(send_messages).tag(message.chat.id)

    threading.Thread(target=bot.infinity_polling, name='bot_infinity_polling', daemon=True).start()
    while True:
        schedule.run_pending()
        time.sleep(1)


