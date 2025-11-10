from fpdf import FPDF
from datetime import datetime
from flask import send_file
import os

class PDF(FPDF):
    process_number = ""
    start_time = ""
    serial_number = ""
    end_time = ""

    def setValues(self, process_number, start_time, serial_number, end_time):
        self.process_number = process_number
        self.start_time = start_time
        self.serial_number = serial_number
        self.end_time = end_time

    def header(self):
        self.set_font('Arial', 'B', 8)
        self.cell(0, 13, '', 0, 1, 'C')

    def add_table(self, data, filename, file_counter, interval=None):
        # ---- Header Row with Left Info, Logo, Right Info ----
        left_info = [
            f"PROCESS PILOT : ICA",
            f"Project Number : ICA",
            f"Serial Number : ICA",
            f"User Name : ica@ica.com"
        ]

        # Use the first and last row timestamps for start/end
        right_info = [
            f"Process Start Time : {data[0]['Date & Time']}",
            f"Process End Time   : {data[-1]['Date & Time']}",
            f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Interval : {interval if interval is not None else '-'}",
        ]

        # Ensure logo path exists
        img_path = os.path.join(os.getcwd(), "static", "logo.png")

        self.set_font("Arial", "", 11)

        # page usable width (excluding margins)
        page_width = self.w - 20
        left_w = page_width * 0.30
        center_w = page_width * 0.30
        right_w = page_width * 0.40

        max_lines = max(len(left_info), len(right_info))

        for i in range(max_lines):
            self.set_x(10)  # left margin

            # ---- Left block ----
            if i < len(left_info):
                self.cell(left_w, 8, left_info[i], 0, 0, "L")
            else:
                self.cell(left_w, 8, "", 0, 0, "L")

            # ---- Center block (logo once) ----
            if i == 1 and os.path.exists(img_path):
                y_now = self.get_y()
                x_center = 10 + left_w + (center_w - 40) / 2
                self.cell(center_w, 20, "", 0, 0, "C")  # reserve space
                self.image(img_path, x=x_center, y=y_now-3, w=40)
            else:
                self.cell(center_w, 8, "", 0, 0, "C")

            # ---- Right block ----
            if i < len(right_info):
                x_now = self.get_x()
                y_now = self.get_y()
                self.multi_cell(right_w, 8, right_info[i], 0, "R")
                self.set_xy(x_now + right_w, y_now)
                self.ln(8)
            else:
                self.cell(right_w, 8, "", 0, 1, "R")

        self.ln(10)

        # ---- Table Header (NO Batch ID as requested) ----
        self.set_font("Arial", "B", 9)
        headers = [
            "S.no", "Date(DD/MM/yyyy)", "Time(HH:MM:SS)",
            "Motor Rpm", "Torque", "Tool Speed(RPM)",
            "Current(Amp)", "Temperature(c)",
            "Pressure Low", "Drive Trip", "Motor PTC", "Temp Sensor"
        ]
        widths = [12, 28, 28, 25, 20, 32, 28, 28, 32, 28, 28, 28, 32]

        table_width = sum(widths)
        page_width = self.w - 20
        x_start = (page_width - table_width) / 2 + 10
        self.set_x(x_start)
        for h, w in zip(headers, widths):
            self.cell(w, 8, h, 1, 0, "C")
        self.ln()

        # ---- Table Body ----
        self.set_font("Arial", "", 9)

        def fmt_num(v):
            try:
                return str(round(float(v), 2))
            except Exception:
                return ""

        for i, row in enumerate(data, start=1):
            # "Date & Time" provided by /report (client_new.py)
            try:
                dt_obj = datetime.strptime(row["Date & Time"], "%Y-%m-%d %H:%M:%S")
                date_str = dt_obj.strftime("%d/%m/%Y")
                time_str = dt_obj.strftime("%H:%M:%S")
            except Exception:
                date_str, time_str = row.get("Date & Time", ""), ""

            # alarm flags are separate columns (0/1)
            press_low  = "Active" if row.get("Pressure Low Alarm", 0) else ""
            drive_trip = "Active" if row.get("Drive Trip Alarm", 0) else ""
            motor_ptc  = "Active" if row.get("Motor PTC Alarm", 0) else ""
            temp_sens  = "Active" if row.get("Temperature Sensor Alarm", 0) else ""

            values = [
                str(i),
                date_str,
                time_str,
                fmt_num(row.get("Motor Speed")),
                fmt_num(row.get("Motor Torque")),
                fmt_num(row.get("Tool Speed")),
                fmt_num(row.get("Motor Current")),
                fmt_num(row.get("Product Temperature")),
                press_low,
                drive_trip,
                motor_ptc,
                temp_sens
            ]

            self.set_x(x_start)
            for v, w in zip(values, widths):
                self.cell(w, 8, v, 1, 0, "C")
            self.ln()

        # ---- Save PDF ----
        self.output(filename)


def print_db_to_pdf(
    batch_data,
    filename_override=None,
    process_number=None,
    start_time=None,
    serial_number=None,
    end_time=None,
    file_counter=0,
    interval=None
):
    """
    Render a PDF for the given batch_data (list of dict rows).
    - filename_override: optional custom filename (e.g., from /report?filename=...)
    - All other metadata args are kept for compatibility (unused in table).
    """
    print("printing....")

    pdf = PDF('L', 'mm', 'A3')  # Landscape, millimeters, A3
    pdf.setValues(process_number, start_time, serial_number, end_time)
    pdf.add_page()

    # Use provided filename or generate one
    if filename_override and isinstance(filename_override, str) and filename_override.strip():
        # Ensure .pdf extension
        if not filename_override.lower().endswith(".pdf"):
            filename = f"{filename_override}.pdf"
        else:
            filename = filename_override
    else:
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f'report_data_{now_str}.pdf'

    pdf.add_table(batch_data, filename, file_counter, interval)
    mimetype = 'application/pdf'
    return send_file(filename, mimetype=mimetype, download_name=filename, as_attachment=True)