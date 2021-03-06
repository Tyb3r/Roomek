import re
import mysql.connector
from mysql.connector import errorcode
import logging
import tokens
import sys
import emoji
import datetime

from settings import reset_db_at_start
from schemas import user_scheme, db_scheme, offer_scheme, db_utility_scheme, conversations_scheme, ratings_scheme, \
    query_scheme, districts_scheme, weights_scheme

# logging.basicConfig(level='DEBUG')
"""Funtion definition"""


class DB_Connection():

    def __init__(self, db_config, DB_NAME):
        self.db_config = db_config
        self.db_name = DB_NAME

    def __enter__(self):
        self.cnx = mysql.connector.connect(**self.db_config)
        self.cursor = self.cnx.cursor(buffered=True, dictionary=True)
        self.cursor.execute("USE {}".format(self.db_name))
        return self.cnx, self.cursor

    def __exit__(self, *args):
        self.cnx.close()


def set_up_db(db_config):
    try:
        cnx = mysql.connector.connect(**db_config)
        cursor = cnx.cursor()
        logging.info("Connection: OK")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error("Something is wrong with your user name or password")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logging.error("Database does not exist")
        else:
            logging.error(str(err))
    try:
        cursor.execute("CREATE DATABASE {} "
                       "DEFAULT CHARACTER SET utf8mb4".format(DB_NAME))
        logging.info("Database created")
    except mysql.connector.Error as err:
        if "database exists" in str(err):
            logging.info(f"Database {DB_NAME} exists.")
        else:
            logging.info("Failed creating database: {}".format(err))
    except UnboundLocalError:
        logging.info("No connection estabilished")
        sys.exit()
    try:
        cursor.execute("USE {}".format(DB_NAME))
        logging.info(f"Database in use: {DB_NAME}")
    except mysql.connector.Error as err:
        logging.error("Failed choosing database: {}".format(err))

    for table_name in db_tables:
        table_description = db_tables[table_name]
        try:
            cursor.execute(table_description)
            logging.info(f"Created table: {table_name}")
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                logging.info(f"Table '{table_name}' already exists.")
            else:
                logging.error(str(err.msg))
        # TODO po co to?
        # else:
        #     logging.info("OK")
    cnx.close()


def create_offer(item):
    """ Creates an offer DB record.

    A function that reads the offer object received from the Scrapy framework, read all of the object
    data and inputs the data into the MySQL table.

    Args:
        item: A scrapy.item object, that contains all of the scraped data.
    """
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        try:
            if type(item).__name__ == 'OfferItem' or type(item).__name__ == 'OfferRoomItem':
                fields_to_insert_into_offers = str(list(item.keys()))
                fields_to_insert_into_offers = re.sub("""[[']|]""", '', fields_to_insert_into_offers)
                s_to_insert_into_offers = ('%s,' * len(item.keys()))[:-1]
                add_query = ("INSERT INTO offers "
                             "(%s) "
                             "VALUES (%s)" % (fields_to_insert_into_offers, s_to_insert_into_offers))
                values = []
                for val in item.values():
                    values.append(val[0])
                cursor.execute(add_query, values)
        except mysql.connector.IntegrityError as err:
            logging.error("Error: {}".format(err))
        cnx.commit()


def create_table_scheme(table_name, table_scheme, primary_key='facebook_id', defaults=False):
    sql_query = db_scheme["beggining"]["text"].format(table_name=table_name)
    for field_name, field_values in table_scheme.items():
        if defaults:
            addition = f" `{field_name}` {field_values['db']} DEFAULT  {field_values['default']},"
        else:
            addition = f" `{field_name}` {field_values['db']},"
        sql_query = ''.join((sql_query, addition))

    sql_query = sql_query + " `creation_time` datetime default current_timestamp, `modification_time` datetime on update current_timestamp, "
    sql_query = sql_query + '' + db_scheme["end"]["text"].format(primary_key=primary_key)
    return sql_query


def create_message(msg_obj, update=False):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        fields_to_add = ''
        msg_data = []

        for field_name in conversations_scheme.keys():
            try:
                if isinstance(getattr(msg_obj, field_name), list) or isinstance(getattr(msg_obj, field_name), dict):
                    if field_name == 'text' or field_name == 'messaging':
                        value = str(getattr(msg_obj, field_name))
                        try:
                            value = emoji.demojize(value)
                        except TypeError:
                            try:
                                value = msg_obj.sticker_name
                            except:
                                value = 'failed_sticker'
                        msg_data.append(value)
                    else:
                        msg_data.append(str(getattr(msg_obj, field_name)))
                else:
                    if field_name == 'text' or field_name == 'messaging':
                        value = getattr(msg_obj, field_name)
                        try:
                            value = emoji.demojize(value)
                        except TypeError:
                            try:
                                value = msg_obj.sticker_name
                            except:
                                value = 'failed_sticker'
                        msg_data.append(value)
                    else:
                        msg_data.append(getattr(msg_obj, field_name))
                fields_to_add = fields_to_add + f',{field_name}'
            except AttributeError:
                logging.info(f"Message had no attribute {field_name} while saving.")

        fields_to_add = fields_to_add[1:]
        placeholders = '%s,' * len(fields_to_add.split(','))
        placeholders = placeholders[:-1]
        try:
            if update:
                duplicate_condition = ''
                for field in fields_to_add.split(','):
                    duplicate_condition = duplicate_condition + field + '=%s,'
                duplicate_condition = duplicate_condition[:-1]
                query = f"""
                            INSERT INTO conversations
                            ({fields_to_add})
                            VALUES ({placeholders})
                            ON DUPLICATE KEY UPDATE {duplicate_condition}
                         """
                cursor.execute(query, msg_data * 2)
            else:
                query = """INSERT INTO conversations
                        ({})
                        VALUES ({})""".format(fields_to_add, placeholders)
                cursor.execute(query, msg_data)
            cnx.commit()
        except:
            logging.debug(f"Message not able to be saved")


# TODO uniwersalne nie powinno korzystac z offer_url
def create_record(table_name, field_name, field_value, offer_url):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """
            INSERT INTO {0}
            (offer_url, {1})
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE {1}=%s
         """.format(table_name, field_name)
        cursor.execute(query, (offer_url, field_value, field_value))
        cnx.commit()


# TODO uproscic uniwersalnym create_record
def create_districts(city, districts):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        for district in districts:
            query = """
                INSERT INTO districts
                (id, city, district, searches)
                VALUES (%s, %s, %s, 0)
            """
            try:
                cursor.execute(query, (f"{city}_{district}", city, district))
                cnx.commit()
            except mysql.connector.errors.IntegrityError as e:
                logging.warning(f"Record already in Districts database ({e}).")


# TODO uproscic uniwersalnym create_record
def create_query(facebook_id, query_no=1):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """
            INSERT INTO queries
            (query_no, facebook_id)
            VALUES (%s, %s)
         """
        cursor.execute(query, (query_no, facebook_id))
        cnx.commit()


def update_query(facebook_id, field_name, field_value, query_no=1):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        if field_name == 'district':
            query_to_get_all_current_offers = """SELECT district
                     FROM queries
                     WHERE facebook_id = %s
                     """ % ("'" + facebook_id + "'",)
            cursor.execute(query_to_get_all_current_offers)
            districts_in_db = cursor.fetchone()['district']
            if districts_in_db:
                if field_value not in districts_in_db:
                    field_value = districts_in_db + ',' + field_value

        query = f"""
            INSERT INTO queries
            (query_no, facebook_id, {field_name})
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE {field_name}=%s
         """

        cursor.execute(query, (query_no, facebook_id, field_value, field_value))
        cnx.commit()
        logging.info(f"Query.{field_name} = '{field_value}' ({facebook_id})")


def create_rating(rating):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        fields = list(rating.keys())
        values = list(rating.values())

        fields_to_insert = ','.join(fields)
        placeholders = ','.join(['%s'] * len(values))

        duplicate_condition = ''
        for field in fields:
            duplicate_condition = duplicate_condition + field + '=%s,'
        duplicate_condition = duplicate_condition[:-1]

        query = f"""
                    INSERT INTO ratings
                    ({fields_to_insert})
                    VALUES ({placeholders})
                    ON DUPLICATE KEY UPDATE {duplicate_condition}
                 """
        cursor.execute(query, values * 2)
        cnx.commit()


def create_user(user_obj=None, update=False):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        fields_to_add = ''
        user_data = []
        for field_name in user_scheme.keys():
            try:
                if isinstance(getattr(user_obj, field_name), list) or isinstance(getattr(user_obj, field_name), dict):
                    user_data.append(str(getattr(user_obj, field_name)))
                else:
                    user_data.append(getattr(user_obj, field_name))
                fields_to_add = fields_to_add + f',{field_name}'
            except AttributeError:
                logging.info(f"User {user_obj['facebook_id']} had no attribute {field_name} while saving.")

        fields_to_add = fields_to_add[1:]
        placeholders = '%s,' * len(fields_to_add.split(','))
        placeholders = placeholders[:-1]

        if update:
            duplicate_condition = ''
            for field in fields_to_add.split(','):
                duplicate_condition = duplicate_condition + field + '=%s,'
            duplicate_condition = duplicate_condition[:-1]

            query = f"""
                        INSERT INTO users
                        ({fields_to_add})
                        VALUES ({placeholders})
                        ON DUPLICATE KEY UPDATE {duplicate_condition}
                     """
            cursor.execute(query, user_data * 2)
        else:

            query = """INSERT INTO users
                    ({})
                    VALUES ({})""".format(fields_to_add, placeholders)
            cursor.execute(query, user_data)
        cnx.commit()


def get_all(table_name='offers', fields_to_get='*'):
    """ Gets all off rows from DB.

    A function that wraps MySQL query into a python function. It lets you to easly return
    all rows of the specified fields from the DB

    Args:
        fields_to_get: A list of strings containing all of fields, that you want to return:
        e.g. fields_to_get = ['offer_url', 'price']

    Returns:
        A list of dictionaries, that cover all of the fields required by the input.
        e.g. input of fields_to_get = ['offer_url', 'price'] would return:
        [{'offer_url': 'abc.html', 'price': 1500}, {'offer_url': 'def.html', 'price': 2000},...]
    """
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        fields_to_get_str = str(fields_to_get)
        fields_to_get_clean = re.sub("""[[']|]""", '', fields_to_get_str)
        query = """SELECT %s
                 FROM %s
                 """ % (fields_to_get_clean, table_name)
        cursor.execute(query)
        result = cursor.fetchall()
        return result


def get(table='offers', fields_to_get='*', amount_of_items=None, fields_to_compare=None, value_to_compare_to=None,
        comparator=None):
    """ Gets rows from DB that meet the specific criteria.

    A function that wraps MySQL query into a python function. It lets you to easly return
    rows of the specified fields from the DB, that meet the specific criteria set up by the user.

    A function call of:

    get(fields_to_get = ['city', 'price'], amount_of_items = 5, fields_to_compare = ['city', 'price'],
        value_to_compare_to = [['lodz', 'poznan'], 1500], comparator = [['=', '='], '<'])

    would generate a MySQL query of:

    SELECT
        city, price
    FROM
        offers
    WHERE
        city = 'lodz' OR city = 'poznan' AND price < 1500

    and would return something similar to:

    [{'city': 'lodz', 'price': 1000}, {'city': 'poznan', 'price': 750},...]

    Args:
        fields_to_get: A list of strings containing all of fields, that you want to return:
        e.g. fields_to_get = ['offer_url', 'price']

        amount_of_items: An integer number that specifies how many items should be returned.

        fields_to_compare: a list of strings that name the fields you want to compare
        e.g. fields_to_compare = ['city', 'price']

        value_to_compare_to: a list of values and/or lists of values that specifies the values you want to compare
        your fields to
        e.g. value_to_compare_to = [['lodz', 'poznan'], 1500] would compare fields_to_compare[0] to either
        'lodz' OR 'poznan' and fields_to_compare[1] to 1500

        comparator: a list of strings and/or lists of strings that specifies the way you want to compare
        e.g. comparator = comparator = [['=', '='], '<'] would compare fields_to_compare[0] to either
        something EQUALTO or something EQUALTO and fields_to_compare[1] to something LESS THAN

    Returns:
        A list of dictionaries, that cover all of the fields required by the input.
    """

    if fields_to_compare is None:
        fields_to_compare = []
    if value_to_compare_to is None:
        value_to_compare_to = []
    if comparator is None:
        comparator = []

    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        fields_to_get_str = str(fields_to_get)
        fields_to_get_clean = re.sub("""[[']|]""", '', fields_to_get_str)
        if type(fields_to_compare) is not list:
            fields_to_compare = [fields_to_compare]
        for value in range(len(value_to_compare_to)):
            if type(value_to_compare_to[value]) is not list:
                value_to_compare_to[value] = [value_to_compare_to[value]]
        for compar in range(len(comparator)):
            if type(comparator[compar]) is not list:
                comparator[compar] = [comparator[compar]]
        if type(comparator) is not list:
            comparator = [comparator]

        comparative_string = ''

        if len(fields_to_compare) != 0:
            comparative_string = ''.join([comparative_string, 'where'])
            for field in range(len(fields_to_compare)):
                for value in range(len(value_to_compare_to[field])):
                    comparative_string = ' '.join(
                        [comparative_string, fields_to_compare[field], comparator[field][value]])
                    comparative_string = ''.join(
                        [comparative_string, """'""", str(value_to_compare_to[field][value]), """'"""])
                    if value != len(value_to_compare_to[field]) - 1:
                        comparative_string = ' '.join([comparative_string, 'or'])
                if field != len(value_to_compare_to[field]):
                    comparative_string = ' '.join([comparative_string, 'and'])

        query = """SELECT 
                        %s
                    FROM 
                        %s
                    %s
                    """ % (fields_to_get_clean, table, comparative_string)
        # TODO -> change in a MySQL secure way
        cursor.execute(query)
        if amount_of_items:
            return cursor.fetchmany(amount_of_items)
        else:
            return cursor.fetchall()


def get_like(like_field, like_phrase, fields_to_get='*'):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        fields_to_get_str = str(fields_to_get)
        fields_to_get_clean = re.sub("""[[']|]""", '', fields_to_get_str)
        like_phrase = "'" + like_phrase + "'"
        query = """SELECT 
                            %s
                        FROM 
                            offers
                        WHERE
                            %s
                        LIKE
                            %s
                        """ % (fields_to_get_clean, like_field, like_phrase)
        cursor.execute(query)
        return cursor.fetchall()


def get_custom(sql_query):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = sql_query
        cursor.execute(query)
        return cursor.fetchall()


def get_query(facebook_id, field_name, query_no=1):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """SELECT %s
                 FROM queries
                 WHERE facebook_id = %s
                 """ % (field_name, "'" + facebook_id + "'")  # TODO change

        logging.debug(f"Query is: {query}")
        cursor.execute(query)
        data = cursor.fetchone()
        return data[field_name]


def get_all_queries(facebook_id, query_no=1):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """SELECT *
                 FROM queries
                 WHERE facebook_id = %s
                 """ % ("'" + facebook_id + "'")  # TODO change
        cursor.execute(query)
        data = cursor.fetchone()
        return [[x, y] for x, y in data.items() if
                (x != 'creation_time' and x != 'modification_time' and y is not None)]


def get_user_data(facebook_id):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """SELECT *
                 FROM users
                 WHERE facebook_id = %s
                 """ % ("'" + facebook_id + "'")  # TODO change

        cursor.execute(query)
        data = cursor.fetchone()
        return data


def get_messages(facebook_id):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """SELECT *
                 FROM conversations
                 WHERE facebook_id = %s
                 """ % (facebook_id)
        cursor.execute(query)
        data = cursor.fetchall()
        # created_messages = []
        # created_message = Message(json_data={'entry': 'default'})
        # for message in data:
        #     for field_name, field_value in message.items():
        #         setattr(created_message, field_name, message[field_name])
        #     created_messages.append(created_message)
        return data


def update_field(table_name, field_name, field_value, where_field, where_value, if_null_required=False):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """
           UPDATE {}
           SET {}=%s
           WHERE {}=%s
        """.format(table_name, field_name, where_field)
        if if_null_required:
            query = query + 'AND ' + field_name + ' IS NULL'
        cursor.execute(query, (field_value, where_value))
        cnx.commit()


def update_user(facebook_id, field_to_update, field_value, if_null_required=False):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = """
           UPDATE users
           SET {}=%s
           WHERE facebook_id=%s
        """.format(field_to_update)
        if if_null_required:
            query = query + 'AND ' + field_to_update + ' IS NULL'
        cursor.execute(query, (field_value, facebook_id))
        cnx.commit()
        logging.info(f"User.{field_to_update} = '{field_value}' ({facebook_id})")


def user_exists(facebook_id):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        query = f"SELECT * FROM users WHERE facebook_id = '{facebook_id}'"

        cursor.execute(query)
        data = cursor.fetchone()

        if data:
            return True
        else:
            return False


def drop_user(facebook_id=None):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        try:
            query = f"""Delete from users where facebook_id = {facebook_id}"""
            cursor.execute(query)
            cnx.commit()
            logging.info(f"User {facebook_id} has just been removed from the USERS database.")
        except mysql.connector.Error as error:
            logging.warning("Failed to delete record from table: {}".format(error))
        try:
            query = f"""Delete from queries where facebook_id = {facebook_id}"""
            cursor.execute(query)
            cnx.commit()
            logging.info(f"User {facebook_id} has just been removed from the QUERIES database.")
        except mysql.connector.Error as error:
            logging.warning("Failed to delete record from table: {}".format(error))


def execute_custom(query, *args, **kwargs):
    with DB_Connection(db_config, DB_NAME) as (cnx, cursor):
        try:
            cursor.execute(query)
            cnx.commit()
        except mysql.connector.Error as error:
            logging.warning("Failed to execute custom command: {}".format(error))


"""DATA"""

DB_NAME = 'RoomekBot$offers'
db_tables = {'offers': create_table_scheme(table_name='offers', table_scheme=offer_scheme, primary_key='offer_url'),
             'utility': create_table_scheme(table_name='utility', table_scheme=db_utility_scheme,
                                            primary_key='offer_url'),
             'users': create_table_scheme(table_name='users', table_scheme=user_scheme),
             'conversations': create_table_scheme(table_name='conversations', table_scheme=conversations_scheme,
                                                  primary_key='conversation_no'),
             'ratings': create_table_scheme(table_name='ratings', table_scheme=ratings_scheme, primary_key='offer_url'),
             'districts': create_table_scheme(table_name='districts', table_scheme=districts_scheme, primary_key='id'),
             'queries': create_table_scheme(table_name='queries', table_scheme=query_scheme, primary_key='facebook_id'),
             'weights': create_table_scheme(table_name='weights', table_scheme=weights_scheme,
                                            primary_key='modification_time', defaults=True),
             }

"""SETUP"""
db_config = tokens.sql_config
set_up_db(db_config)
if reset_db_at_start:
    execute_custom("DROP TABLE users")
    user_table_query = create_table_scheme(table_name='users', table_scheme=user_scheme)
    execute_custom(query=user_table_query)
    execute_custom("DROP TABLE queries")
    queries_table_query = create_table_scheme(table_name='queries', table_scheme=query_scheme,
                                              primary_key='facebook_id')
    execute_custom(query=queries_table_query)
    execute_custom("DROP TABLE weights")
    queries_table_query = create_table_scheme(table_name='weights', table_scheme=query_scheme,
                                              primary_key='modification_time', defaults=True)
    execute_custom(query=queries_table_query)

execute_custom(f"INSERT INTO `roomekbot$offers`.`weights` (`modification_time`) VALUES ('2019-12-01 00:00:0');")
