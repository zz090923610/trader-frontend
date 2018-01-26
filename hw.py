import os

import paho.mqtt.client as mqtt
import paho.mqtt.publish as s_publish
import tornado.ioloop
import tornado.web
import tornado.websocket

live_web_sockets = set()
URL = {"host": "127.0.0.1", "port": 1883}
AUTH = {'username': "zz090923610", 'password': "90q9d3"}


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
            print(payload)
            if "alive" in payload:
                return
            (source, info) = payload.split("/", 1)
            if source == "TradeDaemon":
                (title, content) = info.split("_", 1)
                if title == "heartbeat" and content == 'started':
                    pass
                elif title == "status":
                    if content == "sleep":
                        STATUS_HDL.status = "mqtt_active"
                    elif content == "wait_verify_code":
                        STATUS_HDL.status = "prelogin"
                    elif content == "active":
                        STATUS_HDL.status = "active"
                        web_socket_send_message("active")
            elif source == "TradeAPI":
                if info == 'verify_image_sent':
                    web_socket_send_message('verify_image_sent')
                elif info == "login_success":
                    web_socket_send_message("login_success")
                elif "heartbeat_success" in info:
                    web_socket_send_message("active")
                elif "login_failed" in info:
                    self.change_status("mqtt_active")


MQTT_HDL = MQTTHdl()


def simple_publish(topic, payload, host, port, auth=AUTH):
    s_publish.single(topic, payload=payload, qos=0, retain=False, hostname=host,
                     port=port, client_id="", keepalive=60, will=None, auth=auth,
                     tls=None, protocol=mqtt.MQTTv31)


def valid_trade_action(action_str):
    param_list = action_str.split("_")
    print(param_list)
    if len(param_list) != 4:
        return "Empty fields"
    elif param_list[0] not in ["buy", "sell"]:
        return "Action invalid"
    elif len(param_list[1]) != 6:
        return "Invalid symbol"
    elif float(param_list[2]) <= 0:
        return "Invalid price"
    elif param_list[3][-2:] != '00':
        return "Invalid quantity"
    else:
        return "valid"


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def data_received(self, chunk):
        pass

    def check_origin(self, origin):
        return True

    def open(self):
        live_web_sockets.add(self)

    def on_message(self, message):
        (msg_type, msg_content) = message.split("/", 1)
        if msg_type == "trade":
            check_res = valid_trade_action(msg_content)
            print(check_res)
            if check_res == "valid":
                simple_publish("trade_req", msg_content, URL["host"], URL["port"])
                web_socket_send_message("Trade fired")
            else:
                web_socket_send_message("Invalid Trade with: " + check_res)
        elif msg_type == "exit":
            simple_publish("trade_req", exit, URL["host"], URL["port"])

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

    def login_to_mqtt_server(self, url, user, passwd):
        URL["host"] = url.split(":")[0]
        URL["port"] = int(url.split(":")[1])
        AUTH["username"] = user
        AUTH["password"] = passwd
        MQTT_HDL.client.connect(URL["host"], URL["port"], 60)
        MQTT_HDL.client.loop_start()
        self.change_status("mqtt_active")
        simple_publish("trade_req", "status", URL["host"], URL["port"])

    def change_status(self, new_status):
        STATUS_HDL.status = new_status
        if STATUS_HDL.status == "mqtt_off":
            self.render("html/mqtt_login.html")
        elif STATUS_HDL.status == "mqtt_active":
            self.render("html/prelogin.html")
        elif STATUS_HDL.status == "prelogin":
            self.render("html/verify_code.html")
        elif STATUS_HDL.status == "active":
            self.render("html/trader.html")

    def get(self):

        self.change_status(STATUS_HDL.status)

    def prelogin(self):
        try:
            os.remove("html/verify_code.png")
        except FileNotFoundError:
            pass
        print(URL["host"], URL["port"])
        simple_publish("trade_req", "prelogin", URL["host"], URL["port"])
        self.change_status("prelogin")

    def login_with_verify_code(self, code):
        print(URL["host"], URL["port"])
        simple_publish("trade_req", "login_%s" % code, URL["host"], URL["port"])
        self.change_status("active")
        try:
            os.remove("html/verify_code.png")
        except FileNotFoundError:
            pass

    def post(self):
        behavior = self.get_body_argument("behavior")
        if behavior == "login_to_mqtt_server":
            self.login_to_mqtt_server(self.get_body_argument("url"), self.get_body_argument("user"),
                                      self.get_body_argument("passwd"))
        elif behavior == 'prelogin':
            self.prelogin()
        elif behavior == "login_with_verify_code":
            self.login_with_verify_code(self.get_body_argument("VCODE"))


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
