import os
import threading

import paho.mqtt.client as mqtt
import paho.mqtt.publish as s_publish
import time
import tornado.ioloop
import tornado.web
import tornado.websocket

live_web_sockets = set()
URL = {"host": "127.0.0.1", "port": 1883}
AUTH = {'username': "", 'password': ""}


class MQTTHdl:
    def __init__(self):
        self.client = mqtt.Client()
        self.mqtt_topic_sub = "trade_res/#"
        self.mqtt_topic_pub = "trade_req"
        self.client.on_connect = self.mqtt_on_connect
        self.client.on_message = self.mqtt_on_message
        self.host = None
        self.port = None
        self.auth = None

    def mqtt_on_connect(self, mqttc, obj, flags, rc):
        self.client.username_pw_set(self.auth['username'], self.auth['password'])
        if type(self.mqtt_topic_sub) == list:
            for t in self.mqtt_topic_sub:
                mqttc.subscribe(t)
        elif type(self.mqtt_topic_sub) == str:
            mqttc.subscribe(self.mqtt_topic_sub)
        web_socket_send_message("STATUS_MQTT_CONNECTED")

    def mqtt_on_message(self, mqttc, obj, msg):
        topic = msg.topic

        if topic == "trade_res/img":
            with open("html/verify_code.png", "wb") as f:
                f.write(msg.payload)
                web_socket_send_message("verify_img_ready")
        elif topic == "trade_res/str":
            payload = msg.payload.decode('utf8')
            print(payload)
            web_socket_send_message(payload)
            if "TradeAPI/login_failed" in payload:
                try:
                    os.remove("html/verify_code.png")
                except FileNotFoundError:
                    pass

    def set_msg(self, url, user, passwd):
        self.host = url.split(":")[0]
        self.port = int(url.split(":")[1])
        self.auth = {
            "username": user,
            "password": passwd
        }

    def start(self):
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()

    def publish(self, topic, payload):
        self.client.publish(topic, payload)


MQTT_HDL = None  # MQTTHdl() # NONE FIXME


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)

    def data_received(self, chunk):
        pass

    def check_origin(self, origin):
        return True

    def open(self):
        live_web_sockets.add(self)
        global MQTT_HDL
        if MQTT_HDL is None:
            web_socket_send_message("STATUS_MQTT_OFF")
        else:
            url = "%s:%s" % (MQTT_HDL.host, MQTT_HDL.port)
            web_socket_send_message("STATUS_MQTT_ON_%s" % url)

    def on_message(self, message):
        self.handle_ws_msg(message)

    def on_close(self):
        live_web_sockets.remove(self)

    def handle_ws_msg(self, msg):
        global MQTT_HDL
        if "trader_req" not in msg:
            return
        msg = msg.split("/")[1]
        args = msg.split("_")
        print(msg, args)

        if ("ACTION_MQTT_LOGIN" in msg) & (len(args) == 6):
            print("MQTT connecting")
            if MQTT_HDL is not None:
                try:
                    MQTT_HDL.client.disconnect()
                except Exception:
                    pass
            MQTT_HDL = MQTTHdl()
            MQTT_HDL.set_msg(args[3], args[4], args[5])
            MQTT_HDL.start()
        elif "ACTION_MQTT_DISCONNECT" in msg:

            if MQTT_HDL is not None:
                try:
                    MQTT_HDL.client.disconnect()
                except Exception:
                    pass
            MQTT_HDL = None
            web_socket_send_message("STATUS_MQTT_OFF")
        elif "ACTION_GET_VERIFY_CODE" in msg:
            if MQTT_HDL is None:
                web_socket_send_message("STATUS_MQTT_OFF")
            else:
                MQTT_HDL.publish("trade_req", "prelogin")
        elif "ACTION_RESEND_VERIFY_CODE" in msg:
            if MQTT_HDL is None:
                web_socket_send_message("STATUS_MQTT_OFF")
            else:
                MQTT_HDL.publish("trade_req", "resend_verify_image")
        elif "ACTION_SUBMIT_VERIFY_CODE" in msg:
            if MQTT_HDL is None:
                web_socket_send_message("STATUS_MQTT_OFF")
            else:
                MQTT_HDL.publish("trade_req", "login_%s" % args[-1])
        elif ("ACTION_TRADE" in msg) & (len(args) == 6):
            MQTT_HDL.publish('trade_req',"_".join(args[2:]))
        elif "ACTION_SERVER_STOP" in msg:
            if MQTT_HDL is None:
                web_socket_send_message("STATUS_MQTT_OFF")
            else:
                web_socket_send_message("STATUS_MQTT_CONNECTED")
                MQTT_HDL.publish("trade_req", "exit")
        elif "ACTION_GET_CASH" in msg:
            if MQTT_HDL is None:
                web_socket_send_message("STATUS_MQTT_OFF")
            else:
                MQTT_HDL.publish("trade_req", "cash")


def web_socket_send_message(message):
    removable = set()
    for ws in live_web_sockets:
        if not ws.ws_connection or not ws.ws_connection.stream.socket:
            removable.add(ws)
        else:
            ws.write_message(message)
    for ws in removable:
        live_web_sockets.remove(ws)


class MainHandler(tornado.web.RequestHandler):
    def data_received(self, chunk):
        pass

    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)

    def get(self):
        self.render("html/index.html")

    def post(self):
        pass


def make_app():
    settings = {
        "static_path": "html/assets"
    }
    return tornado.web.Application([
        (r"/", MainHandler),
        (r'/websocket', WebSocketHandler),
        (r"/(.*)", tornado.web.StaticFileHandler, {"path": "html"})
    ], autoreload=True, debug=True, **settings)


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
