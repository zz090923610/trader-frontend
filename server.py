import os

import paho.mqtt.client as mqtt
import paho.mqtt.publish as s_publish
import tornado.ioloop
import tornado.web
import tornado.websocket

live_web_sockets = set()
URL = {"host": "127.0.0.1", "port": 1883}
AUTH = {'username': "", 'password': ""}


class StatusHdl:
    def __init__(self):
        self.status_dict = {
            "mqtt_off": ["mqtt_login"],
            "mqtt_active": ["prelogin"],
            "prelogin": ["login_with_verify_code"],
            "active": ["buy", "sell", "cash"]
        }
        self.status = "mqtt_off"


STATUS_HDL = StatusHdl()


class MQTTHdl:
    def __init__(self):
        self.client = mqtt.Client()
        self.mqtt_topic_sub = "trade_res/#"
        self.mqtt_topic_pub = "trade_req"
        self.client.on_connect = self.mqtt_on_connect
        self.client.on_message = self.mqtt_on_message
        self.client.username_pw_set(AUTH['username'], AUTH['password'])

    def mqtt_on_connect(self, mqttc, obj, flags, rc):
        if type(self.mqtt_topic_sub) == list:
            for t in self.mqtt_topic_sub:
                mqttc.subscribe(t)
        elif type(self.mqtt_topic_sub) == str:
            mqttc.subscribe(self.mqtt_topic_sub)

    def mqtt_on_message(self, mqttc, obj, msg):
        topic = msg.topic
        if topic == "trade_res/img":
            with open("html/verify_code.png", "wb") as f:
                f.write(msg.payload)
        elif topic == "trade_res/str":
            payload = msg.payload.decode('utf8')
            web_socket_send_message(payload)

    def login_to_mqtt_server(self, url, user, passwd):
        URL["host"] = url.split(":")[0]
        URL["port"] = int(url.split(":")[1])
        AUTH["username"] = user
        AUTH["password"] = passwd
        MQTT_HDL.client.connect(URL["host"], URL["port"], 60)
        MQTT_HDL.client.loop_start()

    def publish(self, topic, payload):
        self.client.publish(topic, payload)


MQTT_HDL = MQTTHdl()


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def data_received(self, chunk):
        pass

    def check_origin(self, origin):
        return True

    def open(self):
        live_web_sockets.add(self)

    def on_message(self, message):
        MQTT_HDL.publish("trade_req", message)

    def on_close(self):
        live_web_sockets.remove(self)


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
        (r'/websocket', WebSocketHandler)
    ], autoreload=True, debug=True, **settings)


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
