from fpdf import FPDF
import os
import re

def clean_text(text):
    try:
        # Replace emojis with text
        text = text.replace('✅', '[PASS]').replace('❌', '[FAIL]')
        # Remove other non-latin-1 characters
        return text.encode('latin-1', 'replace').decode('latin-1')
    except Exception as e:
        print(f"Error cleaning text: {e}")
        return "Error cleaning text"

def create_pdf(report_path, output_path):
    print(f"Starting PDF generation from {report_path} to {output_path}")
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        print("PDF object created")
        
        with open(report_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        print(f"Read {len(lines)} lines")
            
        for i, line in enumerate(lines):
            try:
                original_line = line.strip()
                if not original_line:
                    pdf.ln(5)
                    continue
                
                clean_line = clean_text(original_line)
                
                if original_line.startswith("# "):
                    pdf.set_font("Arial", "B", 16)
                    pdf.cell(0, 10, clean_line[2:], ln=True)
                    pdf.set_font("Arial", size=12)
                elif original_line.startswith("## "):
                    pdf.set_font("Arial", "B", 14)
                    pdf.cell(0, 10, clean_line[3:], ln=True)
                    pdf.set_font("Arial", size=12)
                elif original_line.startswith("### "):
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, clean_line[4:], ln=True)
                    pdf.set_font("Arial", size=12)
                else:
                    # Handle long lines
                    pdf.multi_cell(0, 5, clean_line)
            except Exception as e:
                print(f"Error processing line {i}: {e}")
                
        print("Finished processing lines. Saving PDF...")
        pdf.output(output_path)
        print(f"PDF generated successfully at: {output_path}")
    except Exception as e:
        print(f"Error generating PDF: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    report_file = r"c:\Users\Vinay\.gemini\antigravity\scratch\kotak_algo_bot\testsprite_tests\testsprite-mcp-test-report.md"
    # Fallback to raw report if final one doesn't exist
    if not os.path.exists(report_file):
        report_file = r"c:\Users\Vinay\.gemini\antigravity\scratch\kotak_algo_bot\testsprite_tests\tmp\raw_report.md"
        
    # output_file = r"c:\Users\Vinay\Downloads\TestSprite_Report.pdf"
    output_file = "TestSprite_Report.pdf" # Save to current dir first
    
    if os.path.exists(report_file):
        create_pdf(report_file, output_file)
    else:
        print(f"Report file not found: {report_file}")

if __name__ == "__main__":
    report_file = r"c:\Users\Vinay\.gemini\antigravity\scratch\kotak_algo_bot\testsprite_tests\testsprite-mcp-test-report.md"
    # Fallback to raw report if final one doesn't exist
    if not os.path.exists(report_file):
        report_file = r"c:\Users\Vinay\.gemini\antigravity\scratch\kotak_algo_bot\testsprite_tests\tmp\raw_report.md"
        
    output_file = r"c:\Users\Vinay\Downloads\TestSprite_Report.pdf"
    
    if os.path.exists(report_file):
        create_pdf(report_file, output_file)
    else:
        print(f"Report file not found: {report_file}")
