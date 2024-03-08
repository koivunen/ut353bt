# ut353bt
UT353BT Decibel Logging via Bluetooth to MQTT/SQLite

## Requirements
- [UT353BT](https://meters.uni-trend.com/product/ut353-ut353bt/) Decibel Logger
- Bluetooth
- [Python 3.12](https://www.python.org/downloads/) or greater
- [Poetry](https://python-poetry.org/docs/#installing-with-the-official-installer)
    ```bash
    # Linux
    curl -sSL https://install.python-poetry.org | python3 -
    # Windows
    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

    ```
- [Bleak](https://github.com/hbldh/bleak#installation) compatible OS (Windows and Linux are fine at least)

## Installation

```bash
$ poetry install
```

## Usage

```bash
$ poetry run python ut353bt.py --help                         
usage: ut353bt.py [-h] [--wal] [--no-disk-log] [--debug] [--fulldebug] [--interval INTERVAL] [--mac MAC]

options:
  --debug              enable debug logging
  --interval INTERVAL  Sleep interval between measurement requests
  --mac MAC            Only connect to this MAC
  --no-disk-log        Disable disk logging
  --no-mqtt            Disable MQTT

$ poetry run python ut353bt.py       
2024-03-08 20:13:14 MYPC ut353bt[17008] INFO FOUND: UT353BT (E8:D0:3C:AF:EC:AF)


```

**Env params:**

```bash
export MQTT_HOST=10.0.0.1
```

## Database

```bash
$sqlite3 .\ut353bt-e8d03cafe.db .dump

CREATE TABLE timeseries (
                id integer primary key,
                time integer default (cast(strftime('%s','now') as int)),
                decibels REAL
                ) STRICT;
INSERT INTO timeseries VALUES(1,1709919840,36.700000000000002841);
INSERT INTO timeseries VALUES(2,1709919840,36.600000000000001421);
INSERT INTO timeseries VALUES(3,1709919840,36.5);
...
```

## MQTT

TODO

## TODO

- Refactor into a library and make MQTT/DB into tools/examples
- Handle custom modes (for example stop logging to prevent failed data)
- Store voltage levels?
- RSSI
- Aggregate data to min/max automatically
- `--discover`
- Multi device logging


## Similar tools

- https://github.com/Frankkkkk/python-uni-t-ut353-bt
- https://github.com/daweizhangau/esphome_uni_trend_sound_meter
- https://github.com/tigerot/PyQtSoundMeter


## Device specifications

| **Specifications**  	| **UT353BT**  	|
|---------------------	|--------------	|
| Noise (A weighting) 	| 30~130dB     	|
| Accuracy            	| ±1.5dB       	|
| Resolution          	| 0.1dB        	|
| Sampling rate       	| Fast: 125ms  	|
|                     	| Slow: 1000ms 	|
| Frequency response  	| 31.5Hz~8kHz  	|
