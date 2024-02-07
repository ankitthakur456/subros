import datetime
import requests
import time
import socket
from pyfanuc import pyfanuc
from database import DBHelper
from ingeniousLib.logMan import ILogs, LogCleaner

# import logging
# import logging.handlers
# from logging.handlers import TimedRotatingFileHandler

# # region Logging Configuration
# # dirname = os.path.dirname(os.path.abspath(__file__))
#
# log_level = logging.INFO
#
# FORMAT = ('%(asctime)-15s %(levelname)-8s %(name)s %(module)-15s:%(lineno)-8s %(message)s')
#
# logFormatter = logging.Formatter(FORMAT)
# log = logging.getLogger("HIS_LOGS")
#
# # checking and creating logs directory here
#
# if getattr(sys, 'frozen', False):
#     dirname = os.path.dirname(sys.executable)
# else:
#     dirname = os.path.dirname(os.path.abspath(__file__))
#
# logdir = f"{dirname}/logs"
# print(f"log directory name is {logdir}")
# if not os.path.isdir(logdir):
#     log.info("[-] logs directory doesn't exists")
#     try:
#         os.mkdir(logdir)
#         log.info("[+] Created logs dir successfully")
#     except Exception as e:
#         log.error(f"[-] Can't create dir logs Error: {e}")
#
# # fileHandler = TimedRotatingFileHandler(os.path.join(logdir, f'/app_log'),
# #                                        when='midnight', interval=1)
# fileHandler = TimedRotatingFileHandler(f'{logdir}/app_log',
#                                        when='midnight', interval=1)
# fileHandler.setFormatter(logFormatter)
# fileHandler.suffix = "%Y-%m-%d.log"
# log.addHandler(fileHandler)
#
# consoleHandler = logging.StreamHandler()
# consoleHandler.setFormatter(logFormatter)
# log.addHandler(consoleHandler)
#
# log.setLevel(log_level)
#
# # endregion

log = ILogs('HIS_LOGS', 'info', True, True, 'app_log')
log_cleaner = LogCleaner(10)

SAMPLE_RATE = 1

SEND_DATA = False

MACHINE_LIST = [
    'MI-49',
    'MI-42',
    'MI-75',
    'MI-79',
    'MI-61',
    'MI-66',
    'MI-54',
    # 'MI-88',
    'GDR-17',
    'GDR-18',
    # 'ALA-49',
    'GDR 4'
]

machine_obj = {}

token_list = {
    'MI-49': 'mWeAMT1mP55cOQ6Opx3i',
    'MI-42': 'VUR2iHU4GiUguuTlHARc',
    'MI-75': '7t0tsxqEMfN2XiGPZzmA',
    'MI-79': 'BxlqEyQmQyzy5KhJgoK2',
    'MI-61': 'qaqSLAF8Yo7w4g8p4Yo0',
    'MI-66': 'ut8G1cVD5YQPWTGXS7XD',
    'MI-54': 'Vd0o0ibINsT98yJsdccu',
    # 'MI-88': 'F8bs7l3yPy78lBMDvybS',
    'GDR-17': 'yYJKfZL1uueQhQ6KmeAq',
    'GDR-18': 'my0rJQiN2EWtbidwYUtI',
    # 'ALA-49': 'CSRkeUHUtnjHgfp1L6s9',
    'GDR 4': '5UBjIUNSNniUTqSUz835',
}

IP_DICT = {
    'MI-49': '192.168.25.10',
    'MI-42': '192.168.25.12',
    'MI-75': '192.168.25.14',
    'MI-79': '192.168.25.16',
    'MI-61': '192.168.25.18',
    'MI-66': '192.168.25.20',
    'MI-54': '192.168.25.22',
    # 'MI-88': '192.168.25.24',
    'GDR-17': '192.168.25.30',
    'GDR-18': '192.168.25.32',
    # 'ALA-49': '192.168.25.42',
    'GDR 4': '192.168.25.44',
}

machine_emergency_alarm_code = {
    'MI-49': 1003,
    'MI-42': 1003,
    'MI-75': 1004,
    'MI-79': 1004,
    'MI-61': 1003,
    'MI-66': 1003,
    'MI-54': 1003,
    'MI-88': 1004,      # needs to be updated
    'GDR-17': 1004,     # needs to be updated
    'GDR-18': 1037,
    'ALA-49': 1004,     # needs to be updated
    'GDR 4': 1000,
}

HOST = '192.168.25.5'
HEADERS = {'content-type': 'application/json'}

# region API
CYCLE_TIME_API = "/create_cycle_time/"
PART_COUNT_API = "/create_part_count/"
# endregion

IDLE_START_THRESHOLD = 30

log_cleaner.clean()

class FanucCnc:
    def __init__(self, machine_name):
        self.machine_name = machine_name

        # self.log = logging.getLogger(f"{self.machine_name}_log")
        self.log = ILogs(f"{self.machine_name}_log", 'info', True, True)

        # checking and creating logs directory here
        # self.log.addHandler(fileHandler)
        # self.log.addHandler(consoleHandler)
        # self.log.setLevel(logging.INFO)

        self.MACHINE_IP = IP_DICT[self.machine_name]
        self.ACCESS_TOKEN = token_list[self.machine_name]
        self.log.info(f"{self.machine_name} --- {self.MACHINE_IP} --- {self.ACCESS_TOKEN}")
        self.ob_db = DBHelper(self.machine_name)
        self.log.info(f"Trying connection {self.MACHINE_IP}")
        self.conn = pyfanuc(self.MACHINE_IP)

        self.NEW_DATE, self.NEW_SHIFT = self.ob_db.get_misc_data()
        self.GL_MACHINE_STATUS = True  # Machine is running at True
        self.GL_PREV_MACHINE_STATUS = True
        self.GL_PART_COUNT = 0  # for now only 1 else start from 0

        self.GL_PREV_CYCLE_TIME = 0

        self.PART_MODEL = ''
        self.PREV_PART_MODEL = ''
        self.PRECISION = 0.50
        self.CYCLE_TIME = 0
        self.TOLERANCE = self.CYCLE_TIME * self.PRECISION
        self.MIN_CYCT = self.CYCLE_TIME - self.TOLERANCE
        self.MAX_CYCT = self.CYCLE_TIME + self.TOLERANCE
        self.last_machine_cyclet = 0
        self.FL_RESET = False
        self.FL_FIRST_RUN = True

        self.PREV_PART_SENT_TIME = time.time()
        self.GL_PART_CHANGE_TIME = time.time()

        self.FL_CYCLE_RUNNING = False

        # self.INITIAL_COUNTER_FOR_RESET = 0
        # self.CURRENT_COUNTER_FOR_RESET = 0
        # self.FL_PART_RESETTED = False

        self.PREV_OPERATING_TIME = 0
        self.MACHINE_IDLE_STATUS = False
        self.M_STOP_TIME = time.time()
        self.PREV_MACHINE_IDLE_STAT = False

        self.MACHINE_IDLE_ALARM = False
        self.EMERGENCY_ALARM_CODE = machine_emergency_alarm_code[self.machine_name]

        self.axis_dict = {
            'x': 'x_axis',
            'y': 'y_axis',
            'z': 'z_axis',
            'b': 'b_axis'
        }
        self.axis_payload = {}
        self.feedrate = 0
        self.spindle_speed = 0
        self.MACHINE_IDLE_ALARM = False

        self.program_name = ''

        self.PART_COUNT_ING_INIT = True
        self.partCountIng = 0
        self.cPartCountIng = 0
        self.prevCPartCountIng = 0
        # Getting Standard Machine cycle time
        self.get_machine_part_cyct()
        self.reason = ''
        self.prev_reason = ''

        # variables for disconnection alert
        self.disconnected = False
        self.last_con_time = time.time()


        # handling first time run for the misc data table
        prev_d, prev_s = self.ob_db.get_misc_data()
        if prev_d is None or prev_s is None:
            self.get_date_shift()
            self.ob_db.add_misc_data(self.NEW_DATE, self.NEW_SHIFT)
            self.FL_RESET = True
            del prev_d
            del prev_s

    def post_count_data(self, date_, shift, machine_name, part_count, machine_status, reason, idle_status, feedrate,
                        spindle_speed, axis_payload, program_name):
        try:
            url = f'http://{HOST}:8000{PART_COUNT_API}'
            payload = {
                "date_": date_,
                "shift": shift,
                "machine_name": machine_name,
                "start_count": part_count,
                "stop_count": part_count,
                "current_status": machine_status,
                "feed_rate": feedrate,
                "spindle_speed": spindle_speed,
                "idle_status": idle_status,
                "program_name": program_name,
            }

            # axis positions are
            payload.update(axis_payload)
            # because reason was optional so if there is no reason send no reason
            if reason:
                payload['reason'] = reason

            self.log.info(payload)

            if SEND_DATA:
                try:
                    send_req = requests.post(url, json=payload, headers=HEADERS, timeout=2)
                    self.log.info(send_req.status_code)
                    self.log.info(send_req.text)
                    send_req.raise_for_status()
                except Exception as e:
                    self.log.error(f"[-] Error While sending part data error: {e}")
        except Exception as e:
            self.log.error(f'[-] Error while posting data')

    def post_cycle_data(self, date_, shift, machine_name, cycle_time, part_count):
        try:
            url = f'http://{HOST}:8000{CYCLE_TIME_API}'
            payload = {
                "date_": date_,
                "shift": shift,
                "machine_name": machine_name,
                "cycle_time": cycle_time,
                "part_count": part_count
            }
            self.log.info(payload)
            if SEND_DATA:
                try:
                    send_req = requests.post(url, json=payload, headers=HEADERS, timeout=2)
                    self.log.info(send_req.status_code)
                    self.log.info(send_req.text)
                    send_req.raise_for_status()
                except Exception as e:
                    self.log.error(f"[-] Error While sending cycle data error: {e}")
        except Exception as e:
            self.log.error(f'[-] Error while posting data')

    def get_date_shift(self):
        url = f'http://{HOST}:8000/get_current_date_and_shift/'
        try:
            req = requests.get(url, headers=HEADERS, timeout=2)
            attribute_payload = req.json()
            self.log.info(f"[+] got values --- {attribute_payload}")
            if attribute_payload:
                date_ = attribute_payload.get('date_')
                shift = attribute_payload.get('shift')
                if date_:
                    self.NEW_DATE = date_
                if shift:
                    self.NEW_SHIFT = shift
            else:
                self.log.error(f"[-] Error while getting attributes")
        except Exception as e:
            self.log.error(f"[-] {e}")
            return 0

    def get_machine_part_cyct(self):
        url = f'http://{HOST}:8000/get_current_cycle_time/{self.machine_name}'
        try:
            req = requests.get(url, headers=HEADERS, timeout=2)
            attribute_payload = req.json()
            self.log.info(f"[+] got values --- {attribute_payload}")

            if attribute_payload:
                #
                # PART_MODEL = attribute_payload[0].get('part_name')
                # if PART_MODEL is None:
                #     PART_MODEL = ob_db.get_last_part_model()

                self.CYCLE_TIME = attribute_payload.get('standard_cycle_time')
                if (self.CYCLE_TIME is None) or (self.CYCLE_TIME < 1):
                    self.CYCLE_TIME = self.ob_db.get_standard_cycle_time()
            else:
                self.log.error(f"[-] Error while getting standard cycle time and part model")
                self.CYCLE_TIME = self.ob_db.get_standard_cycle_time()

        except Exception as e:
            self.log.error(f"[-] {e}")
            self.CYCLE_TIME = self.ob_db.get_standard_cycle_time()

        if self.CYCLE_TIME:
            self.CYCLE_TIME = int(self.CYCLE_TIME)
        else:
            self.CYCLE_TIME = 0

        self.log.info(f"CYCLE_TIME is {self.CYCLE_TIME}")
        self.TOLERANCE = self.CYCLE_TIME * self.PRECISION
        self.MIN_CYCT = self.CYCLE_TIME - self.TOLERANCE
        self.MAX_CYCT = self.CYCLE_TIME + self.TOLERANCE

    def alert_disconnected(self, status):
        headers = {'content-type': 'application/json'}
        url = f'http://localhost:8080/api/v1/{self.ACCESS_TOKEN}/attributes'
        payload = {
            "AlertDisconnected": status
        }
        self.log.info(str(payload))
        try:
            request_response = requests.post(url, json=payload, headers=headers, timeout=1)
            self.log.info(request_response.status_code)
            if request_response.status_code == 200:
                self.log.info("f[+] Attributes Reset successful")
            else:
                self.log.error("[-] Attributes Reset failed")
        except Exception as e:
            self.log.error(f"[-] Error sending alert {e}")

    def get_focas_values(self):
        self.log.info(f"-------------{self.machine_name}-------------")
        try:
            self.log.info(f"[+] FIRST cycle [{self.FL_FIRST_RUN}]")
            # Handling date and shift here
            self.get_date_shift()

            date_, shift = self.ob_db.get_misc_data()
            # prev_model = self.ob_db.get_last_part_model()
            c_cycle_time = self.ob_db.get_standard_cycle_time()

            if self.NEW_DATE and (date_ != self.NEW_DATE):
                self.log.info(f"[+] [Date ]: {date_} -> {self.NEW_DATE} updating")
                self.ob_db.update_curr_date(self.NEW_DATE)
                self.FL_RESET = True

            if self.NEW_SHIFT and (shift != self.NEW_SHIFT):
                self.log.info(f"[+] [Shift ]: {shift} -> {self.NEW_SHIFT} updating")
                self.ob_db.update_curr_shift(self.NEW_SHIFT)
                self.FL_RESET = True

            # if PART_MODEL != prev_model:
            #     self.log.info(f"[Part Model]: {PART_MODEL} -> {prev_model} updating")
            #     self.ob_db.update_part_model(PART_MODEL)
            #     FL_RESET = True

            if self.CYCLE_TIME and (self.CYCLE_TIME != c_cycle_time):
                # self.log.info(f"[+] [Cycle Time]: {bytearray(c_cycle_time)} -> {bytearray(self.CYCLE_TIME)} updating")
                self.log.info(f"[+] [Cycle Time]: {c_cycle_time} -> {self.CYCLE_TIME} updating")
                self.ob_db.update_std_cycle_time(int(self.CYCLE_TIME))

            # Handling Part Count Reset Here
            if self.FL_RESET:
                # shift_start_part_count = self.GL_PART_COUNT
                # self.INITIAL_COUNTER_FOR_RESET = shift_start_part_count
                # self.CURRENT_COUNTER_FOR_RESET = shift_start_part_count

                self.GL_PART_COUNT = 0
                self.partCountIng = self.cPartCountIng
                self.log.info("[+] Part Count Reset Successfull...")
                self.ob_db.save_product_data(self.NEW_DATE, self.NEW_SHIFT, self.GL_PART_COUNT, 0, self.machine_name, '',
                                        time.time(), self.cPartCountIng)
                self.FL_RESET = False

                # Here we are setting the cPartCountIng to 0 because if I don't do this here then if machine was off
                # and was not accessible then cPartCountIng will not be updated and will retain the same value
                # this will be added to the partCountIng column in subsequent shifts because it was not updated
                # so we will set it to 0 here because if machine was off then cPartCountIng will be added
                self.cPartCountIng = 0
                # self.FL_PART_RESETTED = False

                # here we are checking the first cycle because in Rishav sir's code they will be subracting the start count
                # from stop count so if I sent 0 as start count between the shift and then i sent the actual count
                # Then It will cause the efficiency to spike so if pc was off across shifts then I will not send the
                # 0 as start count and will send only the actual count as the start count and then send incremental count
                # and will only send the 0 as start count when code was running continuosly and has not restarted
                # this way what is lost (due to PC arbitrary shutdown and planned stoppage) is lost, but won't cause hyper spikes
                if not self.FL_FIRST_RUN and not self.disconnected:
                    if self.disconnected:
                        self.log.info(f"[+] Machine was disconnected for previous shift until this shift so not sending 0")

                    self.post_count_data(self.NEW_DATE, self.NEW_SHIFT, self.machine_name, 0, True, '', False, 0, 0, {}, self.program_name)

            date_, shift = self.ob_db.get_misc_data()
            self.log.info(f"[+] date_ = {date_} , shift = {shift}")
            # self.log.info(f"[Current Part Model] -- {PART_MODEL}")
            self.log.info(f"[+] [Standard Cycle Times] -- {self.MIN_CYCT} | {self.CYCLE_TIME}  | {self.MAX_CYCT}")

            if self.conn.connect():
                self.log.info("[+] connection established")
                previous_part_count = self.ob_db.get_last_part_count(date_, shift, self.machine_name, '')
                last_cycle_add_time = self.ob_db.get_last_cycle_add_time(date_, shift)
                self.log.info(f"[!] last_cycle_add_time        {last_cycle_add_time}")

                # region Getting currently running program name
                try:
                    prognum = self.conn.readprognum()
                    self.log.info(f"Prognum: {prognum}")

                    current_prog_num = prognum.get('main')
                    if current_prog_num is None:
                        self.program_name = 'UNKNOWN'
                    else:
                        program_list = self.conn.listprog()
                        self.log.info(f"Program list: {program_list}")
                        self.program_name = program_list.get(current_prog_num).get('comment')
                        if not self.program_name:
                            self.program_name = str(current_prog_num)
                        else:
                            if self.program_name == '()':
                                self.program_name = str(current_prog_num)
                            self.log.info(f'program name type is {type(self.program_name)}')
                            self.program_name = self.program_name.replace('(', '').replace(')', '').replace("'", '')
                            self.program_name = f"{self.program_name} ({current_prog_num})"

                    self.log.info(f"[+] Current Running Program Name is {self.program_name}  and number is {current_prog_num}")
                except Exception as e:
                    self.log.error(f"[+] Failed to get program name")
                # endregion

                # region Getting Feedrate, spindle speed, axis positions.
                try:
                    axisnames = self.conn.readaxesnames()
                    axisnames = [axis.lower() for axis in axisnames]
                    self.log.info(f"AxisNames: {axisnames}")
                    axes_pos_all = self.conn.readaxes().get('ABS')
                    self.log.info(f"All abs Axes positions {axes_pos_all}")
                    for index, axis in enumerate(axisnames):
                        self.axis_payload[self.axis_dict[axis]] = axes_pos_all[index]
                    # self.axis_payload = {self.axis_dict[y]: axes_pos_all[x] for x, y in enumerate(axisnames)}
                    self.log.info(f'Axis positions {self.axis_payload}')
                except Exception as e:
                    self.log.error(f'[+] Error getting axis {e}')

                self.feedrate = self.conn.readactfeed()
                self.log.info(f"[+] Feed rate is {self.feedrate}")
                self.spindle_speed = self.conn.readactspindlespeed()
                self.log.info(f"[+] Spindle speed is {self.spindle_speed}")

                # endregion

                # region Getting Part Count, cycle time and operating time here
                n = self.conn.readparam2(0, 6711)
                self.cPartCountIng = n[6711]["data"][0]
                self.log.info(f"cPartCountIng:{self.cPartCountIng}")
                if self.PART_COUNT_ING_INIT:
                    # here we handled reboot across Same shift
                    self.partCountIng = self.ob_db.variableInit(date_, shift, self.machine_name)
                    if self.partCountIng is None:
                        # here we are handling reboot across different shift
                        self.partCountIng = self.cPartCountIng
                    self.PART_COUNT_ING_INIT = False

                self.log.info(f"[+] part_count_ing is {self.partCountIng}")

                if (self.cPartCountIng - self.partCountIng) < 0 or self.GL_PART_COUNT > (self.cPartCountIng - self.partCountIng):

                    # 1. Get mean cycle time and time it was saved
                    # w_mean_cyct = self.ob_db.get_weighted_cycle_time(date_, shift)
                    w_mean_cyct = self.ob_db.get_last_cycle_time(date_, shift)
                    last_cycle_add_time = self.ob_db.get_last_cycle_add_time(date_, shift)

                    self.log.info(f"[+] Last Cycle time : {w_mean_cyct}")
                    self.log.info(f"[+] Last Cycle time update time : {last_cycle_add_time}")
                    self.log.info(f"[+] prevCPartCountIng:{self.prevCPartCountIng}")

                    # 2. Get the New part count that is increased due to the Reset
                    temp_p_count_ing = -self.GL_PART_COUNT
                    temp_part_count = self.cPartCountIng - temp_p_count_ing
                    parts_increased = temp_part_count - self.GL_PART_COUNT
                    self.log.info(f"[+] New part count will be : {temp_part_count}")
                    self.log.info(f"[+] Original Part count is : {self.GL_PART_COUNT}")
                    self.log.info(f"[+] Parts increased :  {temp_part_count} - {self.GL_PART_COUNT} = {parts_increased}")

                    # 3. Get the Parts that should have been increased after the reset
                    c_time_updt_time_diff = (datetime.datetime.now() - last_cycle_add_time).total_seconds()
                    self.log.info(f"[+] Current time and last update time difference is : {c_time_updt_time_diff}")

                    first_cycle_flag = False
                    try:
                        parts_should_have_increased = round(c_time_updt_time_diff / w_mean_cyct)
                        self.log.info(f"[+] Part that should have increased {c_time_updt_time_diff} / {w_mean_cyct} = {parts_should_have_increased}")
                    except ArithmeticError as AE:
                        self.log.error(f"[-] Error calculating the part that should have increased {AE}")
                        self.log.error(f"[+] Setting first cycle flag true")
                        parts_should_have_increased = 0
                        first_cycle_flag = True   # if there is no w_mean_cyct then it is treated as first cycle
                        # parts_should_have_increased = round(c_time_updt_time_diff / (self.CYCLE_TIME + 30))
                        # log.info(f"[+] Part that should have increased {c_time_updt_time_diff} / ({self.CYCLE_TIME} + 30) = {parts_should_have_increased}")

                    # 4. Check if the parts that have increased is less than or equal to the parts that should have increased

                    part_check = (parts_increased <= parts_should_have_increased)
                    self.log.info(f"{parts_increased} <= {parts_should_have_increased} : [{part_check}]")
                    self.log.info(f"[+] first_cycle flag [{first_cycle_flag}]")
                    if first_cycle_flag or part_check:
                        self.log.info(f"[+] Part Increase under limit {part_check}")
                        self.log.info(f"[+] Keeping the Update")
                        self.partCountIng = -self.GL_PART_COUNT
                        self.ob_db.fixIngResetPC(date_, shift, self.machine_name, self.partCountIng)
                    else:
                        self.log.info(f"[-] Part Increase under limit {part_check }")
                        part_delta = self.prevCPartCountIng - self.cPartCountIng
                        self.log.info(f'[+] Part Delta is {part_delta}')
                        if part_delta < 0:
                            self.log.info(f'[+] Part Delta is negative setting to 0')
                            part_delta = 0
                        self.log.info(f'[+] Deleting delta from the part count')
                        self.ob_db.delete_num_of_parts(date_, shift, self.machine_name, part_delta)
                        previous_part_count = self.ob_db.get_last_part_count(date_, shift, self.machine_name, '')
                        self.GL_PART_COUNT = previous_part_count
                        self.log.info(f'[+] Updated part count is {previous_part_count}')

                elif (self.cPartCountIng - self.partCountIng) >= 0:
                    self.GL_PART_COUNT = self.cPartCountIng - self.partCountIng

                self.log.info(f"[+] prevCPartCountIng {self.prevCPartCountIng}")
                self.prevCPartCountIng = self.cPartCountIng
                self.log.info(f"[+] cPartCountIng: {self.cPartCountIng}, PartCount: {self.GL_PART_COUNT}")
                self.log.info(f"[!] previous part count    {previous_part_count}")

                n1 = self.conn.readparam2(0, 6757)  # reading seconds
                n2 = self.conn.readparam2(0, 6758)  # reading minutes
                a = n2[6758]["data"][0]
                b = n1[6757]["data"][0]
                cycle_time = a * 60 + b / 1000

                n1 = self.conn.readparam2(0, 6751)  # reading milliseconds
                n2 = self.conn.readparam2(0, 6752)  # reading minutes
                a = n2[6752]["data"][0]
                b = n1[6751]["data"][0]
                operating_time = a * 60 + b / 1000

                if self.FL_FIRST_RUN:
                    self.PREV_OPERATING_TIME = operating_time
                    self.GL_PREV_CYCLE_TIME = cycle_time
                    self.FL_FIRST_RUN = False
                self.log.info(f"[+] Cycle Time: {self.GL_PREV_CYCLE_TIME} -> {cycle_time}")
                self.log.info(f"[+] Operating Time: {self.PREV_OPERATING_TIME} -> {operating_time}")

                if self.GL_PART_COUNT > 0:
                    self.ob_db.save_product_data(date_, shift, self.GL_PART_COUNT, cycle_time, self.machine_name, '', time.time(), self.partCountIng)

                if self.GL_PART_COUNT > previous_part_count:
                    pass
                    self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT, self.GL_MACHINE_STATUS,
                                         self.reason, self.MACHINE_IDLE_STATUS, self.feedrate, self.spindle_speed,
                                         self.axis_payload, self.program_name)
                # endregion

                # region Handling alarm and breakdown logic here
                al_with_text = self.conn.readalarmcode(-1, 1)
                self.log.info(f"Got These alarms {al_with_text}")

                # When emergency is pressed remove set machine idle flag

                self.MACHINE_IDLE_ALARM = False
                for i in al_with_text:
                    self.log.info(f"Alarm code {i.get('alarmcode')}")
                    if i.get('alarmcode') == self.EMERGENCY_ALARM_CODE:
                        self.MACHINE_IDLE_ALARM = True
                        self.log.info(f"Emergency Alarm detected Setting Idle Alarm True")

                self.reason = ''
                try:
                    for alarm in al_with_text:
                        # print(reason)
                        a = alarm.get('text')
                        acode = alarm.get('alarmcode')

                        text_list = repr(a).split('\\')
                        self.reason += f"({acode}) "
                        if len(text_list):
                            self.reason += text_list[0].replace("b'", "").replace("'", "")
                        self.reason += ' - '

                    self.log.info(f"Alarm Reason is: {self.reason}")
                except Exception as e:
                    self.log.error(f"Error while processing alarm text: {e}")
                # we only want prev_reason to be updated when there is reason and that reason is not emergency alarm
                if self.reason and not self.MACHINE_IDLE_ALARM:
                    self.prev_reason = self.reason

                # reading and Handling Alarms Here
                al1 = self.conn.readalarm()     # When there is no alarm al1 is 0
                self.log.info(f"[+] Alarm {al1}")

                if al1 and not self.MACHINE_IDLE_ALARM:
                    self.GL_MACHINE_STATUS = False
                    # here we are setting the machine idle status to false otherwise it will send first payload with
                    # machine_status false and idle status true if machine was not running which is unwanted behaviour
                    self.MACHINE_IDLE_STATUS = False
                    self.log.info("[-] breakdown started setting machine idle status false")
                else:
                    if self.MACHINE_IDLE_ALARM:
                        self.log.info(f"[-] Got Emergency alarm setting breakdown false machine_status true")
                    self.GL_MACHINE_STATUS = True

                # if self.MACHINE_IDLE_ALARM:
                #     self.log.info(f"[-] Got Emergency alarm setting breakdown false machine_status true")
                #     self.GL_MACHINE_STATUS = True

                self.log.info(f"[+] Machine status is {self.GL_MACHINE_STATUS}")

                if self.GL_MACHINE_STATUS != self.GL_PREV_MACHINE_STATUS:
                    # here if breakdown started just now and both machine status  and machine idle status changed to false:
                    # only for that case send true for both once
                    # here we are checking only machine status because we have added a check earlier so if
                    # machine_status is false idle will also be false
                    if (self.MACHINE_IDLE_STATUS != self.PREV_MACHINE_IDLE_STAT) and (not self.GL_MACHINE_STATUS):
                        # here we are sending machine status true with idle status true when
                        # idle status changed and went from true to false
                        # this will send true and then after some wait it will send false for idle state
                        # this will allow the idle state to be cleared on the backend and
                        # start or stop breakdown
                        self.log.info(f"[+] sending  bkdown status to disable idle time")

                        self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT,
                                             True,
                                             self.prev_reason, True, self.feedrate,
                                             self.spindle_speed,
                                             self.axis_payload, self.program_name)
                        time.sleep(1)
                        self.PREV_MACHINE_IDLE_STAT = self.MACHINE_IDLE_STATUS

                    # we have this if condition here because I need to send False once our status is going from false to true
                    # then wait 1 sec and send True status

                    if self.GL_MACHINE_STATUS:
                        self.log.info(f"[+] sending false bkdown status")

                        self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT,
                                             False,
                                             self.prev_reason, self.MACHINE_IDLE_STATUS, self.feedrate, self.spindle_speed,
                                             self.axis_payload, self.program_name)
                        time.sleep(1)

                        # the reason to use prev_reason in this machine_status is that
                        # if we used self.reason here, when breakdown clears it clears the reason to '',
                        # this will cause this post_count_data to send current_status false with reason = ''
                        # it will clear the breakdown reason from the server so we are using other variable prev_reason
                        # after the breakdown clears we will send the reason using the prev_reason and will only clear
                        # it once the current_status for last cycle with breakdown is sent
                        self.prev_reason = ''
                    self.log.info(f"[+] sending current bkdown status")
                    self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT, self.GL_MACHINE_STATUS,
                                         self.reason, self.MACHINE_IDLE_STATUS, self.feedrate, self.spindle_speed,
                                         self.axis_payload, self.program_name)
                    self.GL_PREV_MACHINE_STATUS = self.GL_MACHINE_STATUS
                # endregion

                self.log.info(f'[+] Machine running: {self.GL_MACHINE_STATUS}')

                # region Handling Idle Time logic here
                # only run this code if there is no breakdown
                # if machine is in breakdown skip idle time check and sending payload for idle state change as
                # we want it to be false when machine is in breakdown
                if self.GL_MACHINE_STATUS:
                    if temp := operating_time > self.PREV_OPERATING_TIME:
                        self.log.info(f'[+] {operating_time} > {self.PREV_OPERATING_TIME} : [{temp}]')
                        self.log.info("[+] Machine not idle")
                        self.PREV_OPERATING_TIME = operating_time
                        self.MACHINE_IDLE_STATUS = False
                        self.M_STOP_TIME = time.time()
                    elif ((operating_time == self.PREV_OPERATING_TIME) and (time.time() - self.M_STOP_TIME) > IDLE_START_THRESHOLD) or self.MACHINE_IDLE_ALARM:
                        self.log.info(f"[+] ({operating_time} == {self.PREV_OPERATING_TIME} and is machine stopped for more than 30 sec ({time.time() - self.M_STOP_TIME > IDLE_START_THRESHOLD})) or machine_idle_alarm {self.MACHINE_IDLE_ALARM}")
                        self.log.info("[-] Machine idle")
                        self.MACHINE_IDLE_STATUS = True
                    elif self.PREV_OPERATING_TIME > operating_time:
                        self.PREV_OPERATING_TIME = operating_time

                    self.log.info(f"Machine IDLE Status is {self.MACHINE_IDLE_STATUS}")

                    if self.MACHINE_IDLE_STATUS != self.PREV_MACHINE_IDLE_STAT:
                        self.log.info("idle status changed sending payload")

                        # we have this if condition here because I need to send True once our status is going from True to false
                        # then wait 1 sec and send false status
                        if not self.MACHINE_IDLE_STATUS:
                            self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT,
                                                 self.GL_MACHINE_STATUS,
                                                 self.reason, True, self.feedrate, self.spindle_speed,
                                                 self.axis_payload, self.program_name)
                            time.sleep(1)

                        self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT, self.GL_MACHINE_STATUS,
                                             self.reason, self.MACHINE_IDLE_STATUS, self.feedrate, self.spindle_speed,
                                             self.axis_payload, self.program_name)
                        self.PREV_MACHINE_IDLE_STAT = self.MACHINE_IDLE_STATUS
                else:
                    self.log.info(f"[+] Machine in breakdown not checking idle time")
                    self.MACHINE_IDLE_STATUS = False
                # endregion

                # region Handling Cycle time here
                if cycle_time > self.GL_PREV_CYCLE_TIME:
                    self.log.info("[*] Cycle Running")
                    self.GL_PREV_CYCLE_TIME = cycle_time
                    self.FL_CYCLE_RUNNING = True

                # elif self.MIN_CYCT < self.GL_PREV_CYCLE_TIME < self.MAX_CYCT and self.FL_CYCLE_RUNNING:
                elif cycle_time == self.GL_PREV_CYCLE_TIME and self.FL_CYCLE_RUNNING:

                    self.log.info(
                        f"prev_cycle_time == cycle_time : [{self.GL_PREV_CYCLE_TIME == cycle_time}] and cycle_was_running"
                    )

                    self.ob_db.add_cycle_time(date_, shift, self.GL_PREV_CYCLE_TIME, self.GL_PART_COUNT)
                    self.last_machine_cyclet = self.GL_PREV_CYCLE_TIME

                    self.post_cycle_data(date_, shift, self.machine_name, self.GL_PREV_CYCLE_TIME, self.GL_PART_COUNT)

                    self.log.info("[*] Cycle Stopped")
                    self.FL_CYCLE_RUNNING = False

                elif self.GL_PREV_CYCLE_TIME > cycle_time < 10:    # cycle time must be less than 10 seconds to reset because multiple machines are there so it can take multiple time
                    self.log.info("[!] Cycle Resetted")
                    self.GL_PREV_CYCLE_TIME = 0
                    self.FL_CYCLE_RUNNING = False
                # endregion

            else:
                self.log.info(f"[-] Disconnected from machine -------[{self.machine_name}]")

            if (time.time() - self.PREV_PART_SENT_TIME) >= 60:
                self.post_count_data(date_, shift, self.machine_name, self.GL_PART_COUNT, self.GL_MACHINE_STATUS,
                                     self.reason, self.MACHINE_IDLE_STATUS, self.feedrate, self.spindle_speed,
                                     self.axis_payload, self.program_name)

                self.PREV_PART_SENT_TIME = time.time()
            self.last_con_time = time.time()
            self.alert_disconnected(False)
            self.disconnected = False
        except socket.timeout as e:
            self.log.info(f"[+] Error connection failed {e}")
            self.disconnected = True
            if (time.time() - self.last_con_time) > 60:
                self.log.info(f"[+] machine last connected: {time.time() - self.last_con_time} seconds ago...")
                self.alert_disconnected(True)
        except Exception as e:
            self.log.error(f"[-] Error While running Program {e}")


if __name__ == "__main__":
    try:
        for machine in MACHINE_LIST:
            try:
                log.info(f"[+] Initializing for machine {machine}")
                machine_obj[machine] = FanucCnc(machine)
                if machine_obj.get(machine):
                    log.info(f"[+] Init Successfull for {machine}...")
                else:
                    log.error(f"[-] Init Failure for {machine}...")
            except Exception as e:
                log.error(f"[-] Error While Initializing {machine}")

        while True:
            for i, obj in machine_obj.items():
                obj.get_focas_values()
                time.sleep(0.1)

    except Exception as e:
        log.error(f"Error Running Program {e}")

