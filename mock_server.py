from pyModbusTCP.server import ModbusServer
import struct, time, random
import parameters  # uses your HOST_IP, PORT, REG_ADDR, REG_NB, SLEEP_TIME

# helpers
def to_modbus_registers(float_list):
    """Convert floats to 16-bit holding registers (low word first for your client)."""
    regs = []
    for f in float_list:
        b = struct.pack(">f", float(f))       # big-endian float
        hi, lo = struct.unpack(">HH", b)      # hi=high word, lo=low word
        regs += [lo, hi]                      # low word first
    return regs

def build_base_values(batch_id):
    """18-float payload that matches your client’s mapping."""
    return [
        float(batch_id),                   # 1: Batch ID
        random.uniform(1200, 3000),        # 2: Motor Speed
        random.uniform(5.0, 20.0),         # 3: Motor Current
        random.uniform(10.0, 90.0),        # 4: Motor Torque
        random.uniform(100, 500),          # 5: Motor Run Hour
        random.uniform(20.0, 80.0),        # 6: Product Temperature
        random.uniform(500, 1500),         # 7: Tool Speed
        random.uniform(30, 180),           # 8: Set Time
        random.uniform(30, 200),           # 9: Actual Time
        random.uniform(1000, 3000),        # 10: Set Tool RPM
        1.0,                               # 11: Machine On
        random.choice([0.0, 1.0]),         # 12: Drive Trip Alarm
        random.choice([0.0, 1.0]),         # 13: Pressure Low Alarm
        random.choice([0.0, 1.0]),         # 14: Motor PTC Alarm
        random.choice([0.0, 1.0]),         # 15: Temp Sensor Alarm
        float(random.randint(1, 5)),       # 16: Interval
        0.0,                               # 17: Process Start
        0.0,                               # 18: Process End
    ]

def jitter(v, pct=0.02):
    try:
        v = float(v); d = v * pct
        return v + random.uniform(-d, d)
    except:  # noqa: E722
        return v

def emit_record(server, values):
    regs = to_modbus_registers(values)
    # sanity: length must match parameters.REG_NB
    if len(regs) != parameters.REG_NB:
        # 18 floats -> 36 regs; warn if mismatch
        print(f"[warn] produced {len(regs)} regs, expected {parameters.REG_NB}")
    server.data_bank.set_holding_registers(parameters.REG_ADDR, regs)
    print("Sent values:", values)

def start_mock_modbus_server():
    server = ModbusServer(host=parameters.HOST_IP, port=parameters.PORT, no_block=True)
    server.start()
    print(f"Mock PLC Modbus server on {parameters.HOST_IP}:{parameters.PORT} "
          f"(addr {parameters.REG_ADDR}, regs {parameters.REG_NB})")

    batches = [1, 2, 3]  # 3 batches; each will emit start, middle, end

    try:
        while True:
            for batch_id in batches:
                base = build_base_values(batch_id)

                # START (start=1, end=0)
                start_vals = base[:]
                start_vals[16] = 1.0; start_vals[17] = 0.0
                for i in [1,2,3,4,5,6,7,9]: start_vals[i] = jitter(start_vals[i], 0.01)
                emit_record(server, start_vals)
                time.sleep(parameters.SLEEP_TIME)

                # MIDDLE (start=0, end=0)
                mid_vals = base[:]
                mid_vals[16] = 0.0; mid_vals[17] = 0.0
                for i in [1,2,3,4,5,6,7,9]: mid_vals[i] = jitter(mid_vals[i], 0.02)
                for alarm_idx in [11,12,13,14]: mid_vals[alarm_idx] = random.choice([0.0, 1.0])
                emit_record(server, mid_vals)
                time.sleep(parameters.SLEEP_TIME)

                # END (start=0, end=1)
                end_vals = base[:]
                end_vals[16] = 0.0; end_vals[17] = 1.0
                for i in [1,2,3,4,5,6,7,9]: end_vals[i] = jitter(end_vals[i], 0.01)
                emit_record(server, end_vals)
                time.sleep(parameters.SLEEP_TIME)

            print("Completed one 3×3 cycle (3 batches × 3 records). Looping...")

    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        print("Mock server stopped")

if __name__ == "__main__":
    start_mock_modbus_server()