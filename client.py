from fpdf import FPDF
from datetime import datetime
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