import argparse,time
import logging,coloredlogs

parser = argparse.ArgumentParser()

parser.add_argument(
	"--wal",
	action="store_true",
	help="Use WAL",
)
parser.add_argument(
	"--no-disk-log",
	action="store_true",
	help="Disable disk log",
)
parser.add_argument(
	"--no-mqtt",
	action="store_true",
	help="Disable MQTT",
)
parser.add_argument(
	"--debug",
	action="store_true",
	help="enable debug",
)
parser.add_argument(
	"--fulldebug",
	action="store_true",
	help="Debug all libraries",
)

parser.add_argument(
	"--interval",
	type=float,default=0.25,
	help="Sleep interval between measurement requests",
)
parser.add_argument(
	"--mac",
	type=str,
	help="Only connect to this MAC",
)

args = parser.parse_args()

log = logging.getLogger("ut353bt")
if args.debug:
	coloredlogs.install(level='DEBUG', logger=log)
else:
	coloredlogs.install(level='INFO', logger=log)
if args.fulldebug:
	coloredlogs.install(level='DEBUG')



import sys,os,re
import asyncio

# required by aiomqtt: https://pypi.org/project/aiomqtt/
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
	from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
	set_event_loop_policy(WindowsSelectorEventLoopPolicy())

import pathlib,datetime,sqlite3
from bleak import BleakScanner
from bleak import BleakClient,BleakGATTCharacteristic
from pprint import pprint
import aiomqtt,json
import sqlite3
import struct


class DBLogger(object):
	"""sqlite3 database per device"""

	def __init__(self,mac="00000000"):
		if args.wal:
			self.conn = sqlite3.connect(f"ut353bt-{mac}.db",isolation_level=None)
			self.conn.execute('pragma journal_mode=wal')
		else:
			self.conn = sqlite3.connect(f"ut353bt-{mac}.db")

		self.db = self.conn.cursor()
		self.db.execute("""CREATE TABLE if not exists timeseries (
		id integer primary key,
		time integer default (cast(strftime('%s','now') as int)),
		decibels REAL
		) STRICT;""")
		self.conn.commit()

	def store_measurement(self,decibels: float):
		self.db.execute("""INSERT INTO timeseries
								(decibels) 
								VALUES (?);""", (decibels,))
		self.conn.commit()

DBLEVEL_MATCHER = re.compile(rb"(\d{1,3}\.[0-9]{1,3})dBA")
assert float(DBLEVEL_MATCHER.search(b'\xaa\xbb\x10\x01;  38.9dBA=4\x00\x04\x1b')[1].decode("ascii"))
def parse_ut353bt_telemetry(data):
	#TODO: battery level
	try:
		unknown1,sep,dispstr,displayed_unit,measurement_speed,measurement_mode,battlev = struct.unpack(">Ib9sbbbH",data)
	except struct.error:
		return False
	
	battlev=battlev/1000

	if sep!=0x3B: # 0x3B=;
		log.debug("unknown separator")
		return False
	if displayed_unit != 61: # =
		log.error("unknown displayed_unit: %s",displayed_unit)
	fast=None
	if measurement_speed==51:
		fast=False
	elif measurement_speed==52:
		fast=True
	else:
		log.error("unknown measurement_speed: %s",measurement_speed)

	mode_hold = measurement_mode & 1 == 1
	mode_unknown = measurement_mode & 2 == 2
	mode_min = measurement_mode & 4 == 4 
	mode_max = measurement_mode & 8 == 8
	#TODO: warn if other bits are set

	flags=[]
	if mode_hold:
		flags+=["hold"]
	if mode_unknown:
		flags+=["unk"]
	if mode_min:
		flags+=["min"]
	if mode_max:
		flags+=["max"]
	if fast:
		flags+=["fast"]

	flags=",".join(flags)
	log.debug(f"TELE: unknown1={unknown1},sep={sep},measurement_speed={measurement_speed},measurement_mode={measurement_mode},battlev={battlev}V | flags={flags}")
	match=DBLEVEL_MATCHER.search(dispstr)
	if not match:
		return False
	
	return (float(match[1]),{
		"batt": battlev/1000,
		"mode_hold": mode_hold,
		"mode_min": mode_min,
		"mode_max": mode_max,
		"fast": fast,
		"flags": flags
	})
	
MQTT_TOPIC=os.getenv("MQTT_TOPIC","ut353bt/{mac}/")
DEVICE_NAME="UT353BT"
DATAOUT_UUID="0000ff02-0000-1000-8000-00805f9b34fb"
DATAIN_UUID="0000ff01-0000-1000-8000-00805f9b34fb"

mqtt_client=False
async def mqtt(tg):
	global mqtt_client
	async with aiomqtt.Client(os.getenv("MQTT_HOST","10.0.0.1")) as client:
			mqtt_client=client
			log.debug("MQTT connected")
			#log.debug("SUB %s",await client.subscribe("test"))
			async for message in client.messages:
					log.debug("MQTT: %s %s",message.topic,message.payload)
					if message.topic.matches("test"):
							tg.create_task(client.publish("pong", payload="hi"))
	mqtt_client=False

async def ut353bt_loop(tg):
	
	devices = await BleakScanner.discover()
	address=args.mac
	if not address:
		for d in devices:
			if d.name==DEVICE_NAME:
				address=d.address
				log.info("FOUND: %s (%s)",d.name,address)
		
		if not address:
			log.error("no devices found")
			return
		
	DEVICE_ID=0 #TODO

	dblogger = False if args.no_disk_log else DBLogger(address.lower().replace(":",""))

	async with BleakClient(address) as client:
		log.debug("connected: %s",client)

		_MQTT_TOPIC=MQTT_TOPIC.replace('{mac}',address).replace('{deviceid}',str(DEVICE_ID))
		first_msg=True
		last_batt=0
		def callback(sender: BleakGATTCharacteristic, data: bytearray):
			#TODO: handle callback errors fatally!!
			nonlocal first_msg
			nonlocal last_batt
			if args.fulldebug:
				log.debug(f"NOTIFY: {sender}: {data}")
			res=parse_ut353bt_telemetry(data) 
			if not res:
				if not first_msg: # First message seems to always be corrupted
					log.error("could not match data: %s",data)	
			else:
				decibels,metadata=res
				log.debug(f"{decibels} dBA")
				if mqtt_client:
					#TODO: RSSI?
					tg.create_task(mqtt_client.publish(_MQTT_TOPIC+"dba", payload=decibels))
					tg.create_task(mqtt_client.publish(_MQTT_TOPIC+"flags", payload=metadata["flags"]))
					if time.time()-last_batt>10:
						last_batt=time.time()
						tg.create_task(mqtt_client.publish(_MQTT_TOPIC+"battery", payload=metadata["batt"]))
				if dblogger:
					dblogger.store_measurement(decibels)
			first_msg=False

		await client.start_notify(DATAOUT_UUID, callback)
		while True:
			# From HCI snoop logging of the official APK
			await client.write_gatt_char(DATAIN_UUID, b'^', response=False) # no response from this one
			await asyncio.sleep(args.interval)

import bleak
async def ut353bt(tg):
	while True:
		try:
			await ut353bt_loop(tg)
		except bleak.exc.BleakDeviceNotFoundError as e:
			log.error("device not found, retrying")
			pass
		except bleak.exc.BleakError as e:
			log.error("device error: %s",e)
			pass
		await asyncio.sleep(1)
				
async def main():
	# Use a task group to manage and await all tasks
	async with asyncio.TaskGroup() as tg:
		tg.create_task(ut353bt(tg))
		if not args.no_mqtt:
			tg.create_task(mqtt(tg))

if __name__ == "__main__":
	asyncio.run(main())
