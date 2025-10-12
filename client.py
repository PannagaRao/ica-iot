from fpdf import FPDF
from datetime import datetime
from flask import send_file
import os

class PDF(FPDF):
    process_number = ""
    start_time = ""
    serial_number = ""
    end_time = ""
    time_interval = ""

    def setValues(self, process_number, start_time, serial_number, end_time, time_interval):
        self.process_number = process_number
        self.start_time = start_time
        self.serial_number = serial_number
        self.end_time = end_time
        self.time_interval = time_interval

    def header(self):
        self.set_font('Arial', 'B', 8)
        self.cell(0, 13, '', 0, 1, 'C')

    def add_table(self, data, filename, file_counter):
        # ---- Header Row with Left Info, Logo, Right Info ----
        left_info = [
            f"PROCESS PILOT : ICA",
            f"Project Number : ICA",
            f"Serial Number : ICA",
            f"User Name : ica@ica.com"
        ]

        right_info = [
            f"Process Start Time : {data[0]['Date & Time']}",
            f"Process End Time   : {data[-1]['Date & Time']}",
            f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Interval : 1"
        ]

        # Calculate column widths
        col_width = self.w / 3  # 3 sections: left, center, right

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
                # after multi_cell we drop to next line, so reset X for next row
                self.set_xy(x_now + right_w, y_now)
                self.ln(8)
            else:
                self.cell(right_w, 8, "", 0, 1, "R")

        self.ln(10)

        # ---- Table Header ----
        self.set_font("Arial", "B", 9)
        headers = [
            "S.no", "Date(DD/MM/yyyy)", "Time(HH:MM:SS)",
            "Motor Rpm", "Torque", "Tool Speed(RPM)",
            "Voltage(v)", "Current(Amp)", "Temperature(c)",
            "Pressure Low", "Drive Trip", "Motor PTC", "Temp Sensor"
        ]
        widths = [12, 28, 28, 25, 20, 32, 28, 28, 32, 28, 28, 28, 32]

        table_width = sum(widths)
        page_width = self.w - 20   # account for margins
        x_start = (page_width - table_width) / 2 + 10

        self.set_x(x_start)  # <-- center start
        for h, w in zip(headers, widths):
            self.cell(w, 8, h, 1, 0, "C")
        self.ln()

        # ---- Table Body ----
        self.set_font("Arial", "", 9)
        for i, row in enumerate(data, start=1):
            try:
                dt_obj = datetime.strptime(row["Date & Time"], "%Y-%m-%d %H:%M:%S")
                date_str = dt_obj.strftime("%d/%m/%Y")
                time_str = dt_obj.strftime("%H:%M:%S")
            except:
                date_str, time_str = row["Date & Time"], ""

            values = [
                str(i),
                date_str,
                time_str,
                str(round(row["Motor Speed"], 2)),
                str(round(row["Motor Torque"], 2)),
                str(round(row["Tool Speed"], 2)),
                "",  # Voltage placeholder
                str(round(row["Motor Current"], 2)),
                str(round(row["Product Temperature"], 2)),
                "Active" if "Pressure Low" in row["Remarks"] else "",
                "Active" if "Drive Trip" in row["Remarks"] else "",
                "Active" if "Motor PTC" in row["Remarks"] else "",
                "Active" if "Temperature Sensor" in row["Remarks"] else ""
            ]

            self.set_x(x_start)
            for v, w in zip(values, widths):
                self.cell(w, 8, v, 1, 0, "C")
            self.ln()

        # ---- Save PDF ----
        self.output(filename)

def print_db_to_pdf(batch_data, process_number=None, start_time=None, serial_number=None, end_time=None,
                    time_interval=None, file_counter=0):
    print("printing....")

    pdf = PDF('L', 'mm', 'A3')# 'L' for landscape mode, 'mm' for unit of measure, 'A3' for page size
    pdf.setValues(process_number, start_time, serial_number, end_time, time_interval)
    pdf.add_page()

    # Set the filename for the PDF file
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f'report_data_{now_str}.pdf'

    pdf.add_table(batch_data, filename, file_counter)
    # Set the MIME type for the PDF file
    mimetype = 'application/pdf'

    # Return the PDF file as a response
    return send_file(filename, mimetype=mimetype, download_name=filename, as_attachment=True)