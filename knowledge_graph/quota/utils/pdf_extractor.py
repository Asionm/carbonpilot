import PyPDF2
import json
import os

def extract_pdf_to_json(pdf_path, output_dir='static'):
    """
    Read PDF file, extract content from each page and save as JSON format
    
    Args:
        pdf_path (str): PDF file path
        output_dir (str): Output directory, default is 'static'
    
    Returns:
        str: Saved JSON file path
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Store content of each page in a list
    pages_content = []
    
    # Open PDF file
    with open(pdf_path, 'rb') as file:
        # Create PDF reader object
        pdf_reader = PyPDF2.PdfReader(file)
        
        # Get total number of pages
        total_pages = len(pdf_reader.pages)
        
        # Iterate through each page
        for page_num in range(total_pages):
            # Get page object
            page = pdf_reader.pages[page_num]
            
            # Extract text from page
            text = page.extract_text()
            
            # Add page content to list
            pages_content.append({
                'page_number': page_num + 1,
                'content': text
            })
    
    # Construct output file path
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_file = os.path.join(output_dir, f'{pdf_name}.json')
    
    # Save content as JSON file
    with open(output_file, 'w', encoding='utf-8') as json_file:
        json.dump(pages_content, json_file, ensure_ascii=False, indent=2)
    
    return output_file