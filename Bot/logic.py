#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Functions for basic bot behaviours. How it reacts to certain messages, depending on the context. """

from settings import *
import tokens
from Databases import mysql_connection as db
import Bot.cognition as cog
import Bot.reactions_pl as rea
from Bot.facebook_webhooks import Bot
from schemas import bot_phrases, query_scheme
import random


bot = Bot(tokens.fb_access)


def handle_message(message, user):
    """ Recognize the content and respond accordingly. """

    db.create_message(msg_obj=message)

    if message.is_echo:
        pass
    else:
        bot.fb_send_action(str(message.facebook_id), 'mark_seen')

        if message.type == "Delivery":
            pass
        elif message.type == "ReadConfirmation":
            pass
        elif message.type == "UnknownType":
            pass
        elif message.type == "TextMessage":
            handle_text(message, user, bot)
        elif message.type == "StickerMessage":
            handle_sticker(message, user, bot)
        elif message.type == "LocationAnswer":
            handle_location(message, user, bot)
        elif message.type == "GifMessage":
            handle_attachment(message, user, bot)
        elif message.type == "MessageWithAttachment":
            handle_attachment(message, user, bot)
        elif message.type == "DevMode":
            handle_devmode(message, user, bot)
        else:
            logging.warning(f"Didn't recognize the message type: {message.type}")


def handle_text(message, user, bot):
    """ React when the user sends any text. """
    if message.NLP:
        logging.info(f"-NLP→ intent: {str(message.NLP_intent)}, entities: {str(message.NLP_entities)}")
        cog.collect_information(message, user, bot)
        respond(message, user, bot)
    else:
        rea.default_message(message, user, bot)


def handle_sticker(message, user, bot):
    """ React when the user sends a sticker. """
    bot.fb_fake_typing(str(message.facebook_id), 0.5)
    response = rea.sticker_response(message, user, bot)
    if response != "already sent":
        bot.fb_send_text_message(str(message.facebook_id), response)
    logging.info(f"Message <sticker> from {str(message.facebook_id)[0:5]} recognized as '{message.sticker_name}' sticker (id={message.stickerID})")
    logging.info(f"Bot's response to user {str(message.facebook_id)} sticker:  '{response}'")


def handle_attachment(message, user, bot):
    """ React when the user sends a GIF, photos, videos, or any other non-text item."""
    if fake_typing: bot.fb_fake_typing(str(message.facebook_id), 0.8)
    image_url = r'https://media.giphy.com/media/L7ONYIPYXyc8/giphy.gif'
    bot.fb_send_image_url(str(message.facebook_id), image_url)
    logging.info(f"Bot's response to user {str(message.facebook_id)} gif:  '<GIF>'")


def handle_location(message, user, bot):
    """ React when the user replies with location."""
    if user.context == "ask_for_city":
        user.add_location(message.latitude, message.longitude, city_known=False)
    elif user.context == "ask_for_location":
        user.add_location(message.latitude, message.longitude, city_known=True)
    respond(message, user, bot)


def handle_devmode(message, user, bot):
    if 'quick' in message.text:
        bot.fb_send_quick_replies(message.facebook_id, "This is a test of quick replies", ['test_value_1', 'test_value_2', 'test_value_3'])
    # elif 'list' in message.text:
    #     bot.fb_send_list_message(message.facebook_id, element_titles=['test_value_1', 'test_value_2'], button_titles=['test_value_3', 'test_value_4'])  # TODO not working
    # elif 'button' in message.text:
    #     bot.fb_send_button_message(message.facebook_id, "test", ['test_value_1', 'test_value_2'])  # TODO not working
    # elif 'generic' in message.text:
    #     bot.fb_send_generic_message(message.facebook_id, ['Test_value_1', 'Test_value_2'])
    elif 'd' in message.text:
        bot.fb_send_text_message(str(message.facebook_id), 'Your data has been erased.')
        db.drop_user(message.facebook_id)
    elif 's' in message.text:
        rea.show_user_object(message, user, bot)
    else:
        bot.fb_send_text_message(str(message.facebook_id), 'Hello world!')


# TODO bug: adding place yes/no returns nothing
def respond(message, user, bot):

    if message.NLP_intent == "greeting":
        rea.greeting(message, user, bot)
    elif not message.NLP_intent and not message.NLP_entities:   # nie zrozumiał, więc ponawia pytanie
        rea.default_message(message, user, bot)
        response2 = random.choice(bot_phrases['back_to_context'])
        bot.fb_send_text_message(str(message.facebook_id), response2)
        ask_for_information(message, user, bot)
    elif message.NLP_intent == "restart":
        rea.ask_if_restart(message, user, bot)
    elif user.wants_restart:
        rea.restart(message, user, bot)
    elif user.wrong_data:
        rea.ask_what_wrong(message, user, bot)
    elif user.confirmed_data:
        rea.show_offers(message, user, bot)
    elif user.wrong_data:
        rea.ask_what_wrong(message, user, bot)
    else:
        ask_for_information(message, user, bot)


def ask_for_information(message, user, bot):

    if db.get_query(user.facebook_id, "business_type") is None:
        rea.ask_for(message, user, bot, param="business_type")

    elif db.get_query(user.facebook_id, "city") is None:
        rea.ask_for(message, user, bot, param="city")

    # TODO not the best approach
    elif user.context == "ask_for_city":
        rea.ask_for_location(message, user, bot)

    elif user.wants_more_locations:
        rea.ask_more_locations(message, user, bot)

    elif db.get_query(user.facebook_id, "housing_type") is None:
        rea.ask_for(message, user, bot, param="housing_type")

    elif db.get_query(user.facebook_id, "total_price") in [None, 0]:
        rea.ask_for(message, user, bot, param="price", meta=f"{db.get_query(user.facebook_id,'business_type')}_{db.get_query(user.facebook_id,'housing_type')}")

    elif user.wants_more_features:
        features_in_schema = [field_name for field_name, field_value in query_scheme.items() if
                              field_value['is_feature']]
        user_features_queried = [query_tuple[0] for query_tuple in db.get_all_queries(facebook_id=user.facebook_id)]
        features_recorded = [i for i in user_features_queried if i in features_in_schema]
        if len(features_recorded) == 0:
            rea.ask_for(message, user, bot, param="features",
                             meta=f"{db.get_query(user.facebook_id, 'housing_type')}")
        else:
            rea.ask_for_more_features(message, user, bot,
                             meta=f"{db.get_query(user.facebook_id, 'housing_type')}")

    elif not user.wants_more_features and not user.confirmed_data:
        rea.show_input_data(message, user, bot)

    # TODO rea.ask_what_wrong(message, user, bot)

    elif user.confirmed_data and not user.wants_restart:
        rea.show_offers(message, user, bot)

    elif user.wants_restart:
        db.drop_user(user.facebook_id)
        rea.restart(message, user, bot)

    else:
        rea.default_message(message, user, bot)
