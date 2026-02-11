from fpdf import FPDF
import datetime
import os

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Kotak Algo Bot - User Guide', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(230, 240, 255)
        self.cell(0, 8, title, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, body):
        self.set_font('Arial', '', 11)
        # Sanitize to ASCII
        safe_body = body.encode('latin-1', 'replace').decode('latin-1')
        self.multi_cell(0, 6, safe_body)
        self.ln()

    def add_image(self, image_path, caption):
        if os.path.exists(image_path):
            try:
                # Convert WebP to PNG if needed
                temp_png = None
                if image_path.lower().endswith('.webp'):
                    from PIL import Image
                    im = Image.open(image_path)
                    # Save as temp png
                    temp_png = image_path.replace('.webp', '.temp.png')
                    im.save(temp_png, 'PNG')
                    image_path_to_use = temp_png
                else:
                    image_path_to_use = image_path

                # Center image
                self.image(image_path_to_use, x=15, w=180)
                self.ln(2)
                self.set_font('Arial', 'I', 9)
                
                # Sanitize caption
                safe_caption = caption.encode('latin-1', 'replace').decode('latin-1')
                self.cell(0, 5, safe_caption, 0, 1, 'C')
                self.ln(5)

                # Cleanup temp file
                if temp_png and os.path.exists(temp_png):
                    os.remove(temp_png)

            except Exception as e:
                print(f"Error adding image {image_path}: {e}")
                self.cell(0, 5, f"[Image: {caption} - Error]", 0, 1, 'C')
        else:
            self.cell(0, 5, f"[Image not found]", 0, 1, 'C')
        self.ln()

pdf = PDF()
pdf.alias_nb_pages()
pdf.add_page()

# Paths to images in artifacts directory
ARTIFACTS_DIR = r"c:\Users\Vinay\.gemini\antigravity\brain\fdfbae9a-cb94-4713-b8ec-77cb1890cd02"
IMG_DASHBOARD = os.path.join(ARTIFACTS_DIR, "verify_ui_dashboard_1770707005783.webp")
IMG_EQUITY = os.path.join(ARTIFACTS_DIR, "verify_dashboard_equity_1770722459720.webp")

# 1. Introduction
pdf.chapter_title('1. Introduction')
pdf.chapter_body(
    "Welcome to the Kotak Algo Bot. This automated trading system is designed to trade on your behalf "
    "in the Nifty and BankNifty markets. It monitors the market 24/7, identifies profitable opportunities "
    "based on pre-defined strategies, and executes trades instantly without human intervention.\n\n"
    "This guide will help you understand how to monitor and control the bot using the visual dashboard."
)

# 2. The Dashboard
pdf.chapter_title('2. The Trading Dashboard')
pdf.chapter_body(
    "The Dashboard is your main control center. It provides a real-time overview of your trading performance "
    "and current market status. Key elements include:"
)
pdf.chapter_body(
    "- Total P&L: Your net profit or loss for the current session.\n"
    "- Win Rate: The percentage of profitable trades.\n"
    "- Capital: Your currently available trading capital.\n"
    "- Active Positions: Trades currently open in the market."
)
pdf.add_image(IMG_DASHBOARD, "Figure 1: Main Dashboard Overview")

# 3. Monitoring Strategies
pdf.chapter_title('3. Monitoring Strategies')
pdf.chapter_body(
    "The bot runs multiple strategies simultaneously. The 'Active Strategies' section lists all running algorithms "
    "(e.g., 'TrendFollowing_Nifty', 'MeanReversion_BankNifty').\n\n"
    "Each card shows:\n"
    "- Status: 'Running' (Green) or 'Paused' (Yellow)\n"
    "- Performance: P&L specific to that strategy\n"
    "- Action: A 'Pause/Resume' button to manually stop a strategy if needed."
)

# 4. Performance Tracking
pdf.chapter_title('4. Tracking Growth (Equity Curve)')
pdf.chapter_body(
    "The Equity Curve chart visualizes the growth of your account over time. A rising curve indicates consistent "
    "profits. Dips represent drawdowns, which are normal in trading. This chart helps you verify that the "
    "bot is performing as expected over the long term."
)
pdf.add_image(IMG_EQUITY, "Figure 2: Performance Equity Curve")

# 5. Safety & Controls
pdf.chapter_title('5. Safety Features')
pdf.chapter_body(
    "The bot includes several safety mechanisms to protect your capital:\n"
    "- Stop Loss: Every trade has a maximum loss limit.\n"
    "- Capital Protection: The bot stops trading if daily loss exceeds a set limit.\n"
    "- Secure Login: Access is protected by OTP authentication (coming soon).\n"
    "- Paper Trading Mode: Allows you to test strategies with virtual money before risking real funds."
)

# Output
output_path = os.path.join(ARTIFACTS_DIR, "Kotak_Algo_Bot_User_Guide.pdf")
pdf.output(output_path)
print(f"PDF generated successfully: {output_path}")
