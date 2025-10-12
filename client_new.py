from flask import Flask, jsonify, render_template, request, redirect
from flask_restful import Resource, Api
import time
import os
import struct
from pyModbusTCP.client import ModbusClient
from sqlalchemy import create_engine, Table, MetaData, Column, Integer, String, Float, delete
from sqlalchemy.orm import sessionmaker
import multiprocessing
from datetime import datetime

import parameters
from client import print_db_to_pdf

DATABASE_URL = "sqlite:///./register_data.db"
engine = create_engine(DATABASE_URL, echo=True)
metadata = MetaData()

# ---- New schema with 18 registers ----
register_data = Table(
    'register_data', metadata,
    Column('id', Integer, primary_key=True),
    Column('timestamp', String(50)),  # system datetime
    *[Column(f'register{i}', Float) for i in range(1, 19)]
)

metadata.create_all(engine)
Session = sessionmaker(bind=engine)

c = ModbusClient(host=parameters.HOST_IP, port=parameters.PORT, auto_open=True)

app = Flask(__name__)
api = Api(app)

# ---------------- REST API ----------------
class DataResource(Resource):
    def get(self):
        print("[API] /data requested")
        data = read_data_from_db()
        key_values = ["id", "timestamp"] + [f"register{i}" for i in range(1, 19)]
        list_of_dicts = [dict(zip(key_values, values)) for values in data]
        return list_of_dicts

api.add_resource(DataResource, '/data')


@app.route('/view')
def view_data():
    print("[ROUTE] /view accessed")
    data = read_data_from_db()
    key_values = ["id", "timestamp"] + [f"register{i}" for i in range(1, 19)]
    list_of_dicts = [dict(zip(key_values, values)) for values in data]
    return render_template('view_data.html', data=list_of_dicts)


# ---------------- Modbus Client ----------------
def modbus_client():
    while True:
        print("[Modbus] Attempting to read registers")
        regs_l = c.read_holding_registers(parameters.REG_ADDR, parameters.REG_NB)
        if regs_l:
            print("[Modbus] Registers received")
            regs_float = []
            for i in range(0, len(regs_l), 2):
                mypack = struct.pack('>HH', regs_l[i + 1], regs_l[i])
                f = struct.unpack('>f', mypack)
                regs_float.append(f[0])
            print("[Modbus] Decoded floats:", regs_float)

            # Trigger condition → use Process End (#18) as last register
            if round(regs_float[-1]) == 1:
                print("[DB] Trigger detected, inserting row into database")
                session = Session()
                ins = register_data.insert().values(
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    **{f'register{i}': regs_float[i - 1] for i in range(1, 19)}
                )
                session.execute(ins)
                session.commit()
                session.close()
                print("[DB] Insert committed successfully")
            else:
                print("[DB] Trigger not set, skipping insert")
        else:
            print("[Modbus] Read error - no data received")
        time.sleep(parameters.SLEEP_TIME)


# ---------------- Database Ops ----------------
def read_data_from_db(page=1, per_page=20):
    session = Session()
    result = session.query(register_data).offset((page - 1) * per_page).limit(per_page).all()
    session.close()
    return result


def delete_data():
    print("[DB] Deleting specific batch")
    session = Session()
    stmt = delete(register_data).where(register_data.c.register1 == batch_id)
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


@app.route('/report')
def report():
    print("[ROUTE] /report accessed")
    filename = request.args.get('filename')
    batch_id = request.args.get('batch_id')

    if not batch_id:
        # fallback: get all rows
        print("[DB] Generating report for all batches")
        session = Session()
        batch_data = session.query(register_data).all()
    else:
        print("[DB] Generating report for batch ID:", batch_id)
        session = Session()
        query = session.query(register_data)
        search_query = f'{batch_id}'
        query = query.filter(register_data.c.register1 == search_query)
        batch_data = query.all()
        session.commit()
        session.close()

        # ---- Build report rows ----
        report_data = []
        for idx, row in enumerate(batch_data, start=1):
            remarks = build_remarks(row)
            print(remarks)

            report_row = {
                "S.no": idx,
                "Date & Time": row.timestamp,
                "Batch ID": row.register1,
                "Motor Speed": row.register2,
                "Motor Current": row.register3,
                "Motor Torque": row.register4,
                "Motor Run Hour": row.register5,
                "Product Temperature": row.register6,
                "Tool Speed": row.register7,
                "Actual Time": row.register9,
                "Remarks": remarks    
            }
            report_data.append(report_row)

        return print_db_to_pdf(report_data, filename, 1)

    return redirect("/view")


def build_remarks(row):
    remarks = []
    if row.register13:  # Pressure Low Alarm
        remarks.append("Pressure Low Alarm active")
    if row.register12:  # Drive Trip Alarm
        remarks.append("Drive Trip Alarm active")
    if row.register14:  # Motor PTC Alarm
        remarks.append("Motor PTC Alarm active")
    if row.register15:  # Temp Sensor Alarm
        remarks.append("Temperature Sensor Alarm active")
    return "; ".join(remarks) if remarks else ""


# ---------------- Delete Endpoints ----------------
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
    if batch_id:
        delete_data()
    return redirect("/view")


@app.route('/del_all')
def del_all():
    print("[ROUTE] /del_all triggered")
    delete_all_data()
    return redirect("/view")


# ---------------- Filter API ----------------
@app.route('/filterData')
def filterData():
    print("[API] /filterData requested")
    draw = request.args.get('draw', type=int)
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    search_value = request.args.get('search[value]', default='')
    order_column = request.args.get('order[0][column]', type=int)
    order_direction = request.args.get('order[0][dir]', default='asc')

    columns = ["id", "timestamp"] + [f"register{i}" for i in range(1, 19)]
    order_column_name = columns[order_column]

    session = Session()
    query = session.query(register_data)

    if search_value:
        global batch_id
        batch_id = search_value
        query = query.filter(register_data.c.register1 == search_value)

    if order_direction == 'desc':
        query = query.order_by(getattr(register_data.c, order_column_name).desc())
    else:
        query = query.order_by(getattr(register_data.c, order_column_name).asc())

    records_total = query.count()
    query = query.offset(start).limit(length)
    data = query.all()

    data_formatted = [
        [getattr(row, column) for column in columns]
        for row in data
    ]

    response = {
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_total,
        'data': data_formatted
    }

    session.close()
    return jsonify(response)


if __name__ == '__main__':
    print("[APP] Starting Modbus background thread and Flask server on port 5050")
    modbus_thread = multiprocessing.Process(target=modbus_client)
    modbus_thread.start()
    app.run(debug=True, host="127.0.0.1", port=5050, use_reloader=False)