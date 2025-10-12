from pyModbusTCP.server import ModbusServer
import struct
import time
import random

def start_mock_modbus_server():
    server = ModbusServer(host="127.0.0.1", port=8502, no_block=True)
    server.start()
    print("Mock PLC Modbus server started on port 8502")

    try:
        while True:
            # Simulate realistic values for 18 registers
            batch_id = random.randint(1, 10)                      # 1
            motor_speed = random.uniform(1200, 3000)              # 2
            motor_current = random.uniform(5.0, 20.0)             # 3
            motor_torque = random.uniform(10.0, 90.0)             # 4
            motor_run_hour = random.uniform(100, 500)             # 5
            product_temp = random.uniform(20.0, 80.0)             # 6
            tool_speed = random.uniform(500, 1500)                # 7
            set_time = random.uniform(30, 180)                    # 8
            actual_time = random.uniform(30, 200)                 # 9
            set_tool_rpm = random.uniform(1000, 3000)             # 10
            machine_on = random.choice([0.0, 1.0])                # 11
            drive_trip_alarm = random.choice([0.0, 1.0])          # 12
            pressure_low_alarm = random.choice([0.0, 1.0])        # 13
            motor_ptc_alarm = random.choice([0.0, 1.0])           # 14
            temp_sensor_alarm = random.choice([0.0, 1.0])         # 15
            interval = random.randint(1, 5)                       # 16
            process_start = random.choice([0.0, 1.0])             # 17
            process_end = 1.0                                     # 18 → trigger for DB insert

            # Combine into float list
            values = [
                float(batch_id), motor_speed, motor_current, motor_torque,
                motor_run_hour, product_temp, tool_speed, set_time,
                actual_time, set_tool_rpm, machine_on, drive_trip_alarm,
                pressure_low_alarm, motor_ptc_alarm, temp_sensor_alarm,
                float(interval), process_start, process_end
            ]

            # Convert to 2-word (16-bit) Modbus registers (big endian float → word swap)
            registers = []
            for f in values:
                b = struct.pack(">f", f)
                h1, h2 = struct.unpack(">HH", b)
                registers += [h2, h1]  # low word first for your client compatibility

            # Write 36 registers starting at address 600
            server.data_bank.set_holding_registers(600, registers)
            print("Sent values:", values)

            time.sleep(10)

    except KeyboardInterrupt:
        server.stop()
        print("Mock server stopped")

if __name__ == "__main__":
    start_mock_modbus_server()
