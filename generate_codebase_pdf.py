import os
from fpdf import FPDF

def create_codebase_pdf(root_dir, output_file):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Configuration
    included_extensions = {'.py', '.js', '.jsx', '.css', '.html', '.md', '.json'}
    excluded_dirs = {'node_modules', '.git', '__pycache__', 'dist', 'build', 'tmp', 'testsprite_tests', '.gemini', 'reports'}
    
    print(f"Scanning codebase at: {root_dir}")
    
    file_count = 0
    
    for root, dirs, files in os.walk(root_dir):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        
        for file in files:
            _, ext = os.path.splitext(file)
            if ext in included_extensions and file != 'package-lock.json': # Skip large lock files
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, root_dir)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Sanitize content for pdf
                    content = content.encode('latin-1', 'replace').decode('latin-1')
                    
                    pdf.set_font("Arial", 'B', 12)
                    pdf.set_text_color(0, 51, 102) # Dark Blue
                    pdf.cell(0, 10, f"File: {rel_path}", ln=True)
                    
                    pdf.set_font("Courier", size=8)
                    pdf.set_text_color(0, 0, 0) # Black
                    pdf.multi_cell(0, 4, content)
                    pdf.ln(5)
                    
                    file_count += 1
                    print(f"Added: {rel_path}")
                    
                except Exception as e:
                    print(f"Skipping {rel_path}: {e}")

    print(f"Total files added: {file_count}")
    pdf.output(output_file)
    print(f"PDF saved to: {output_file}")

if __name__ == "__main__":
    project_root = r"c:\Users\Vinay\.gemini\antigravity\scratch\kotak_algo_bot"
    output_pdf = r"c:\Users\Vinay\Downloads\Kotak_Algo_Bot_Codebase.pdf"
    create_codebase_pdf(project_root, output_pdf)
