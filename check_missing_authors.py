#!/usr/bin/env python3
"""
Quick script to check how many combined XML files are missing author information
"""
import os
import xml.etree.ElementTree as ET

def check_authors(xml_file_path):
    """Check if XML has authors in any format"""
    try:
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        # Check old format
        authors = root.findall('.//atom:author/atom:name', namespaces)
        if authors:
            return 'old_format'
        
        # Check new threading format
        thread = root.find('.//atom:thread', namespaces)
        if thread is not None:
            # Messages ARE in atom namespace too
            messages = thread.findall('./atom:message', namespaces)
            if len(messages) > 0:
                # Double check if messages have authors (author is also in atom ns)
                author_in_msg = thread.find('./atom:message/atom:author', namespaces)
                if author_in_msg is not None:
                    return 'threaded'
        
        return 'missing'
    except Exception as e:
        return f'error: {e}'

def scan_directory(base_dir="static/bitcoin-dev"):
    """Scan all combined XML files"""
    results = {
        'old_format': 0,
        'threaded': 0,
        'missing': 0,
        'error': 0,
        'missing_files': []
    }
    
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.startswith('combined_') and file.endswith('.xml'):
                file_path = os.path.join(root, file)
                status = check_authors(file_path)
                
                if status == 'missing':
                    results['missing'] += 1
                    results['missing_files'].append(file_path)
                elif status == 'old_format':
                    results['old_format'] += 1
                elif status == 'threaded':
                    results['threaded'] += 1
                else:
                    results['error'] += 1
    
    return results

if __name__ == "__main__":
    print("🔍 Scanning for missing authors...")
    results = scan_directory()
    
    total = results['old_format'] + results['threaded'] + results['missing'] + results['error']
    
    print(f"\n📊 Results:")
    print(f"  Total files scanned: {total}")
    print(f"  ✅ Files with threading structure: {results['threaded']}")
    print(f"  ✅ Files with old author format: {results['old_format']}")
    print(f"  ❌ Files missing authors: {results['missing']}")
    print(f"  ⚠️  Files with errors: {results['error']}")
    
    if results['missing'] > 0:
        print(f"\n⚠️  Found {results['missing']} files missing author information!")
        print(f"\nFirst 10 files missing authors:")
        for f in results['missing_files'][:10]:
            print(f"  - {f}")
        
        if len(results['missing_files']) > 10:
            print(f"  ... and {len(results['missing_files']) - 10} more")
    else:
        print(f"\n✅ All files have author information!")

