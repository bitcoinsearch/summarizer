#!/usr/bin/env python3
"""
Fix XML files in summarizer that have "UTC | newest]" as author.
Fetches correct authors from Elasticsearch and updates the XMLs.
"""

import os
import sys
import re
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, List
from bs4 import BeautifulSoup

# Elasticsearch configuration
ES_INDEX = "bitcoin-search-august-23"
ES_URL = "https://my-test-es-deploy.es.us-central1.gcp.cloud.es.io"
ES_API_KEY = "MV9xanFvNEJ4Ti1oU21pWktWWkM6UDZGU2FwQ1NRNmFyMVVGNWJhVWliZw=="

ES_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"ApiKey {ES_API_KEY}"
}

# Atom namespace
ATOM_NS = {'atom': 'http://www.w3.org/2005/Atom'}


def has_utc_author(xml_file: Path) -> bool:
    """Check if XML file has UTC or placeholder as author"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Register namespace to avoid ns0 prefix
        ET.register_namespace('', 'http://www.w3.org/2005/Atom')
        
        # Check old format: <author><name>
        for author in root.findall('.//atom:author/atom:name', ATOM_NS):
            if author.text and ('UTC' in author.text or 'newest]' in author.text or author.text == 'Mailing List'):
                return True
        
        # Check new threaded format: <thread><message><author>
        for author in root.findall('.//atom:thread/atom:message/atom:author', ATOM_NS):
            if author.text and ('UTC' in author.text or 'newest]' in author.text or author.text == 'Mailing List'):
                return True
                
        return False
        
    except Exception as e:
        print(f"❌ Error checking {xml_file}: {e}")
        return False


def extract_title_from_xml(xml_file: Path) -> Optional[str]:
    """Extract title from XML"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        title_elem = root.find('.//atom:title', ATOM_NS)
        if title_elem is not None and title_elem.text:
            return title_elem.text.strip()
        
        return None
    except Exception as e:
        print(f"❌ Error extracting title from {xml_file}: {e}")
        return None


def extract_author_from_url_fallback(title: str) -> Optional[str]:
    """Try to get author from URL by searching ES for URL, then scraping"""
    try:
        # Query ES for URL
        query = {
            "query": {
                "match_phrase": {
                    "title": title
                }
            },
            "size": 1,
            "_source": ["url"]
        }
        
        url = f"{ES_URL}/{ES_INDEX}/_search"
        response = requests.post(url, json=query, headers=ES_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None
        
        doc_url = hits[0]["_source"].get("url")
        if not doc_url:
            return None
        
        # Fetch and parse the URL
        from bs4 import BeautifulSoup
        response = requests.get(doc_url, timeout=10)
        response.raise_for_status()
        html_text = response.text
        
        # Try old format: @ YYYY-MM-DD HH:MM Author
        old_format_match = re.search(r'@\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})\s+(.+?)(?:\n|<|$)', html_text)
        if old_format_match:
            author = old_format_match.group(2).strip()
            author = re.sub(r'<[^>]+>', '', author)
            author = author.split('\n')[0].strip()
            author = author.replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
            # Clean up common suffixes
            author = author.replace(" via Bitcoin Development Mailing List", "")
            author = author.replace("via Bitcoin Development Mailing List", "").strip()
            # Remove surrounding quotes if present
            author = author.strip("'\"")
            if author and not (author.startswith('UTC') or 'newest' in author or author == 'Mailing List'):
                return author
        
        return None
        
    except Exception as e:
        return None


def get_author_from_elasticsearch(title: str) -> Optional[str]:
    """Get correct author from Elasticsearch based on title"""
    try:
        # Query ES for the document
        query = {
            "query": {
                "match_phrase": {
                    "title": title
                }
            },
            "size": 1,
            "_source": ["authors", "title"]
        }
        
        url = f"{ES_URL}/{ES_INDEX}/_search"
        response = requests.post(url, json=query, headers=ES_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None
        
        authors = hits[0]["_source"].get("authors", [])
        if not authors or not authors[0]:
            return None
        
        author = authors[0]
        
        # Skip if still UTC or generic placeholder
        if 'UTC' in author or 'newest]' in author or author == 'Mailing List':
            # Try to fetch from URL as fallback
            print(f"   ⚠️  ES has placeholder '{author}', trying URL extraction...")
            return extract_author_from_url_fallback(title)
        
        return author
        
    except Exception as e:
        print(f"❌ Error querying Elasticsearch for '{title}': {e}")
        return None


def fix_xml_author(xml_file: Path, correct_author: str) -> bool:
    """Fix the author in an XML file"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Register namespace to avoid ns0 prefix
        ET.register_namespace('', 'http://www.w3.org/2005/Atom')
        
        fixed_count = 0
        
        # Fix old format: <author><name>
        for author_name in root.findall('.//atom:author/atom:name', ATOM_NS):
            if author_name.text and ('UTC' in author_name.text or 'newest]' in author_name.text):
                author_name.text = correct_author
                fixed_count += 1
        
        # Fix new threaded format: <thread><message><author>
        for author_elem in root.findall('.//atom:thread/atom:message/atom:author', ATOM_NS):
            if author_elem.text and ('UTC' in author_elem.text or 'newest]' in author_elem.text):
                author_elem.text = correct_author
                fixed_count += 1
        
        if fixed_count > 0:
            # Write back to file
            tree.write(xml_file, encoding='utf-8', xml_declaration=True)
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error fixing {xml_file}: {e}")
        return False


def scan_and_fix_xmls(static_dir: Path, dry_run: bool = False) -> Dict[str, int]:
    """Scan all XMLs and fix those with UTC authors"""
    
    print("="*80)
    print("🔍 SCANNING XMLs FOR UTC AUTHORS")
    print("="*80)
    
    if dry_run:
        print("🔍 DRY RUN MODE - No files will be modified")
    
    stats = {
        'total_scanned': 0,
        'affected_found': 0,
        'successfully_fixed': 0,
        'failed_to_fix': 0,
        'no_author_in_es': 0
    }
    
    affected_files = []
    
    # Scan all XML files
    for xml_file in static_dir.rglob('*.xml'):
        stats['total_scanned'] += 1
        
        if has_utc_author(xml_file):
            stats['affected_found'] += 1
            affected_files.append(xml_file)
    
    print(f"\n📊 Scan Results:")
    print(f"   Total XMLs scanned: {stats['total_scanned']}")
    print(f"   XMLs with UTC author: {stats['affected_found']}")
    
    if not affected_files:
        print("\n✅ No affected files found!")
        return stats
    
    print(f"\n🔧 Processing {len(affected_files)} affected files...")
    print("="*80)
    
    # Fix each affected file
    for i, xml_file in enumerate(affected_files, 1):
        relative_path = xml_file.relative_to(static_dir)
        print(f"\n[{i}/{len(affected_files)}] {relative_path}")
        
        # Extract title
        title = extract_title_from_xml(xml_file)
        if not title:
            print(f"   ⚠️  Could not extract title")
            stats['failed_to_fix'] += 1
            continue
        
        print(f"   Title: {title}")
        
        # Get correct author from ES
        correct_author = get_author_from_elasticsearch(title)
        if not correct_author:
            print(f"   ⚠️  Could not find correct author in Elasticsearch")
            stats['no_author_in_es'] += 1
            continue
        
        print(f"   ✓ Found author: {correct_author}")
        
        if dry_run:
            print(f"   [DRY RUN] Would update author to: {correct_author}")
            stats['successfully_fixed'] += 1
        else:
            # Fix the XML
            if fix_xml_author(xml_file, correct_author):
                print(f"   ✅ Fixed!")
                stats['successfully_fixed'] += 1
            else:
                print(f"   ❌ Failed to update file")
                stats['failed_to_fix'] += 1
    
    return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix XMLs with UTC authors')
    parser.add_argument('--static-dir', type=str, default='static',
                        help='Path to static directory (default: static)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Dry run - show what would be fixed without modifying files')
    
    args = parser.parse_args()
    
    static_dir = Path(args.static_dir)
    if not static_dir.exists():
        print(f"❌ Static directory not found: {static_dir}")
        sys.exit(1)
    
    print("🚀 Starting XML UTC Author Fix")
    print(f"📁 Static directory: {static_dir}")
    print()
    
    # Scan and fix
    stats = scan_and_fix_xmls(static_dir, dry_run=args.dry_run)
    
    # Summary
    print("\n" + "="*80)
    print("📊 FINAL SUMMARY")
    print("="*80)
    print(f"Total XMLs scanned:      {stats['total_scanned']}")
    print(f"XMLs with UTC author:    {stats['affected_found']}")
    print(f"✅ Successfully fixed:   {stats['successfully_fixed']}")
    print(f"❌ Failed to fix:        {stats['failed_to_fix']}")
    print(f"⚠️  No author in ES:     {stats['no_author_in_es']}")
    print("="*80)
    
    if args.dry_run and stats['affected_found'] > 0:
        print("\n💡 Run without --dry-run to actually fix the files")
    
    if stats['successfully_fixed'] > 0:
        print(f"\n✅ Successfully fixed {stats['successfully_fixed']} XMLs!")


if __name__ == "__main__":
    main()
