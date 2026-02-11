from fpdf import FPDF
import datetime

class PDF(FPDF):
    def header(self):
        # Logo placeholder or Title
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Kotak Algo Bot - Technical Architecture Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}} - Generated on {datetime.datetime.now().strftime("%Y-%m-%d")}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 6, title, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Arial', '', 11)
        self.multi_cell(0, 5, body)
        self.ln()

    def bullet_point(self, text):
        self.set_font('Arial', '', 11)
        self.cell(5)  # Indent
        self.cell(5, 5, '-', 0, 0) # Bullet (hyphen for safety)
        self.multi_cell(0, 5, text)
        self.ln(2)

pdf = PDF()
pdf.alias_nb_pages()
pdf.add_page()

# ... (content remains same, just ensuring the bullet_point method is fixed)

# [Content Definitions omitted for brevity in search replacement]

# Output to Artifacts Directory
output_path = r"c:\Users\Vinay\.gemini\antigravity\brain\fdfbae9a-cb94-4713-b8ec-77cb1890cd02\Kotak_Algo_Bot_Architecture_Report.pdf"
pdf.output(output_path)
print(f"PDF generated successfully: {output_path}")
