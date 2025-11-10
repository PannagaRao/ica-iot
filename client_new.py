from flask import Flask, jsonify, render_template, request, redirect
from flask_restful import Resource, Api
import time
import os
import struct
from pyModbusTCP.client import ModbusClient
from sqlalchemy import create_engine, Table, MetaData, Column, Integer, String, Float, delete
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import multiprocessing

import parameters
from client import print_db_to_pdf  # uses the updated client.py below

DATABASE_URL = "sqlite:///./register_data.db"
engine = create_engine(DATABASE_URL, echo=True)
metadata = MetaData()

# ---------------------------
# Schema (retain raw registers; add batch/process/date/time fields)
# ---------------------------
register_data = Table(
    'register_data', metadata,
    Column('id', Integer, primary_key=True),
    Column('timestamp', String(50)),     # "YYYY-MM-DD HH:MM:SS"
    Column('date', String(10)),          # "YYYY-MM-DD"
    Column('time', String(8)),           # "HH:MM:SS"
    Column('batch_id', String(50)),      # from register1
    Column('process_start', Integer),    # from register17 -> 0/1
    Column('process_end', Integer),      # from register18 -> 0/1
    *[Column(f'register{i}', Float) for i in range(1, 19)]
)

metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Modbus client
c = ModbusClient(host=parameters.HOST_IP, port=parameters.PORT, auto_open=True)

app = Flask(__name__)
api = Api(app)


# ---------------- Helpers ----------------
def alarm_bits_from_row(row):
    """Return 4 ints (0/1) from registers 12..15 in the order:
       (drive_trip, pressure_low, motor_ptc, temp_sensor)
    """
    drive_trip   = 1 if getattr(row, "register12", 0) else 0
    pressure_low = 1 if getattr(row, "register13", 0) else 0
    motor_ptc    = 1 if getattr(row, "register14", 0) else 0
    temp_sensor  = 1 if getattr(row, "register15", 0) else 0
    return drive_trip, pressure_low, motor_ptc, temp_sensor


def as_row_list(row):
    """Row -> list in the same order as /filterData columns."""
    drive_trip, pressure_low, motor_ptc, temp_sensor = alarm_bits_from_row(row)
    values = [
        row.id, row.timestamp, row.date, row.time, row.batch_id,
        row.process_start, row.process_end,
        drive_trip, pressure_low, motor_ptc, temp_sensor
    ]
    for i in range(1, 19):
        values.append(getattr(row, f"register{i}", None))
    return values


# ---------------- REST API ----------------
class DataResource(Resource):
    def get(self):
        print("[API] /data requested")
        data = read_data_from_db()
        key_values = (
            ["id", "timestamp", "date", "time", "batch_id", "process_start", "process_end",
             "drive_trip_alarm", "pressure_low_alarm", "motor_ptc_alarm", "temp_sensor_alarm"]
            + [f"register{i}" for i in range(1, 19)]
        )
        payload = []
        for row in data:
            drive_trip, pressure_low, motor_ptc, temp_sensor = alarm_bits_from_row(row)
            row_vals = [
                row.id, row.timestamp, row.date, row.time, row.batch_id,
                row.process_start, row.process_end,
                drive_trip, pressure_low, motor_ptc, temp_sensor
            ] + [getattr(row, f"register{i}", None) for i in range(1, 19)]
            payload.append(dict(zip(key_values, row_vals)))
        return payload

api.add_resource(DataResource, '/data')


@app.route('/view')
def view_data():
    """
    View: report-like table (no interval / start-time / end-time panel).
    Shows Batch filter (optional) and per-row KPIs + four separate alarm columns (0/1).
    """
    print("[ROUTE] /view accessed")
    batch = request.args.get('batch_id')  # optional
    session = Session()
    query = session.query(register_data)
    if batch:
        query = query.filter(register_data.c.batch_id == str(batch))
    rows = query.order_by(register_data.c.id.asc()).all()
    session.close()

    table_rows = []
    for r in rows:
        drive_trip, pressure_low, motor_ptc, temp_sensor = alarm_bits_from_row(r)
        table_rows.append({
            "id": r.id,
            "date": r.date,
            "time": r.time,
            "batch_id": r.batch_id,
            "motor_speed": getattr(r, "register2", None),
            "motor_current": getattr(r, "register3", None),
            "motor_torque": getattr(r, "register4", None),
            "motor_run_hour": getattr(r, "register5", None),
            "product_temperature": getattr(r, "register6", None),
            "tool_speed": getattr(r, "register7", None),
            "actual_time": getattr(r, "register9", None),
            "interval": getattr(r, "register16", None),
            "drive_trip_alarm": drive_trip,
            "pressure_low_alarm": pressure_low,
            "motor_ptc_alarm": motor_ptc,
            "temp_sensor_alarm": temp_sensor,
        })

    # Your template should iterate over 'data' and show the above fields.
    return render_template('view_data.html', data=table_rows, selected_batch=batch or "")


# ---------------- Modbus Client ----------------
def modbus_client():
    while True:
        try:
            print("[Modbus] Attempting to read registers")
            regs_l = c.read_holding_registers(parameters.REG_ADDR, parameters.REG_NB)
            if not regs_l:
                print("[Modbus] Read error - no data received")
                time.sleep(parameters.READ_TIME)
                continue

            # --- Convert 16-bit register pairs into floats (big-endian) ---
            regs_float = []
            for i in range(0, len(regs_l), 2):
                mypack = struct.pack('>HH', regs_l[i + 1], regs_l[i])
                f = struct.unpack('>f', mypack)
                regs_float.append(f[0])

            print("[Modbus] Decoded floats:", regs_float)

            # --- Trigger condition → use Machine On (register 11) ---
            if len(regs_float) >= 11 and round(regs_float[10]) == 1:
                print("[DB] Machine ON detected → inserting row into database")

                # Derived fields
                batch_id = str(int(round(regs_float[0]))) if len(regs_float) >= 1 else ""
                interval_value = regs_float[15] if len(regs_float) >= 16 else None  # register16
                process_start  = int(round(regs_float[16])) if len(regs_float) >= 17 else 0
                process_end    = int(round(regs_float[17])) if len(regs_float) >= 18 else 0

                now = datetime.now()
                ts = now.strftime("%Y-%m-%d %H:%M:%S")
                dt = now.strftime("%Y-%m-%d")
                tm = now.strftime("%H:%M:%S")

                # --- Prepare full row payload ---
                row_payload = {
                    "timestamp": ts,
                    "date": dt,
                    "time": tm,
                    "batch_id": batch_id,
                    "process_start": process_start,
                    "process_end": process_end,
                    "register16": interval_value,
                    **{f"register{i}": regs_float[i - 1] for i in range(1, min(19, len(regs_float) + 1))}
                }

                # --- Insert into DB ---
                session = Session()
                session.execute(register_data.insert().values(**row_payload))
                session.commit()
                session.close()
                print(f"[DB] Inserted row for batch {batch_id} (Machine On=1)")

            else:
                print("[DB] Machine OFF (trigger bit = 0) → skipping insert")

        except Exception as e:
            print(f"[Modbus] Exception: {e}")

        time.sleep(0.5)


# ---------------- DB Ops ----------------
def read_data_from_db(page=1, per_page=50):
    session = Session()
    result = (session.query(register_data)
              .order_by(register_data.c.id.asc())
              .offset((page - 1) * per_page)
              .limit(per_page)
              .all())
    session.close()
    return result


def delete_data(batch_id_value):
    print(f"[DB] Deleting batch {batch_id_value}")
    session = Session()
    stmt = delete(register_data).where(register_data.c.batch_id == str(batch_id_value))
    session.execute(stmt)
    session.commit()
    session.close()


def delete_all_data():
    print("[DB] Deleting all data")
    session = Session()
    stmt = delete(register_data)
    session.execute(stmt)
    session.commit()
    session.close()


# ---------------- Report ----------------
@app.route('/report')
def report():
    print("[ROUTE] /report accessed")
    filename = request.args.get('filename')  # optional override for PDF filename
    batch_id_q = request.args.get('batch_id')

    session = Session()
    if not batch_id_q:
        print("[DB] Generating report for all batches")
        batch_rows = session.query(register_data).order_by(register_data.c.id.asc()).all()
    else:
        print("[DB] Generating report for batch ID:", batch_id_q)
        batch_rows = (session.query(register_data)
                      .filter(register_data.c.batch_id == str(batch_id_q))
                      .order_by(register_data.c.id.asc())
                      .all())
    session.close()

    # ---- Build report rows ----
    report_data = []
    for idx, row in enumerate(batch_rows, start=1):
        drive_trip, pressure_low, motor_ptc, temp_sensor = alarm_bits_from_row(row)
        report_row = {
            "S.no": idx,
            "Date & Time": f"{row.date} {row.time}",
            "Batch ID": row.batch_id,  # present in payload (PDF ignores it per your preference)
            "Motor Speed": getattr(row, "register2", None),
            "Motor Current": getattr(row, "register3", None),
            "Motor Torque": getattr(row, "register4", None),
            "Motor Run Hour": getattr(row, "register5", None),
            "Product Temperature": getattr(row, "register6", None),
            "Actual Time": getattr(row, "register9", None),
            # four separate alarm columns (0/1)
            "Drive Trip Alarm": drive_trip,
            "Pressure Low Alarm": pressure_low,
            "Motor PTC Alarm": motor_ptc,
            "Temperature Sensor Alarm": temp_sensor,
        }
        report_data.append(report_row)

    if report_data:
        # Updated client.print_db_to_pdf supports optional filename override
        interval_value = batch_rows[0].register16 if batch_rows else None
        return print_db_to_pdf(report_data, filename_override=filename, interval=interval_value)

    # fallback to view if nothing to report
    return redirect("/view")


# ---------------- File & Delete Endpoints ----------------
@app.route('/del_file/<filename>')
def del_file(filename):
    print("[ROUTE] /del_file accessed for", filename)
    if os.path.isfile(filename):
        os.remove(filename)
        return "File is removed successfully!"
    else:
        return redirect("/view")


@app.route('/del_batch')
def del_batch():
    print("[ROUTE] /del_batch triggered")
    batch_id_value = request.args.get('batch_id')
    if batch_id_value:
        delete_data(batch_id_value)
    return redirect("/view")


@app.route('/del_all')
def del_all():
    print("[ROUTE] /del_all triggered")
    delete_all_data()
    return redirect("/view")


# ---------------- DataTables-friendly Filter API ----------------
@app.route('/filterData')
def filterData():
    print("[API] /filterData requested")
    draw = request.args.get('draw', type=int)
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    search_value = request.args.get('search[value]', default='')
    order_column = request.args.get('order[0][column]', type=int)
    order_direction = request.args.get('order[0][dir]', default='asc')

    columns = (
        ["id", "timestamp", "date", "time", "batch_id", "process_start", "process_end",
         "drive_trip_alarm", "pressure_low_alarm", "motor_ptc_alarm", "temp_sensor_alarm"]
        + [f"register{i}" for i in range(1, 19)]
    )
    order_column_name = columns[order_column] if order_column is not None and 0 <= order_column < len(columns) else "id"

    session = Session()
    query = session.query(register_data)

    if search_value:
        query = query.filter(register_data.c.batch_id == str(search_value))

    # Derived alarm columns are not DB columns; fall back to id if chosen
    if order_column_name in {"drive_trip_alarm", "pressure_low_alarm", "motor_ptc_alarm", "temp_sensor_alarm"}:
        order_column_name = "id"

    if order_direction == 'desc':
        query = query.order_by(getattr(register_data.c, order_column_name).desc())
    else:
        query = query.order_by(getattr(register_data.c, order_column_name).asc())

    records_total = query.count()
    data = query.offset(start).limit(length).all()

    data_formatted = [as_row_list(row) for row in data]

    response = {
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_total,
        'data': data_formatted
    }

    session.close()
    return jsonify(response)


if __name__ == '__main__':
    print("[APP] Starting Modbus background process and Flask server on port 5050")
    modbus_proc = multiprocessing.Process(target=modbus_client)
    modbus_proc.start()
    app.run(debug=True, host="0.0.0.0", port=5050, use_reloader=False)