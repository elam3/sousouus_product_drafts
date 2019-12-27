import requests
import sys
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pathlib import Path
import os
from woocommerce import API as WC_API
import re
import json
import constant
from size_attribute_terms import product_sizes
from PIL import Image
import io
import datetime
import pprint
import csv

#TODO: Revisit error handling

################################################################################
# scrape.py
#
# Provided a list of product links to sousounetshop.jp, create a skeleton of
# product drafts on wooCommerce.
#
# Specs:
#   - Product title (Japanese)
#   - Product description (Japanese)
#   - Product price (yen)
#   - Product SKU
#   - Product Images
#
# Future Implementations:
#   - Product categorization
#
################################################################################

def main():
    # Read api key/secret
    wcapi_key, wcapi_secret = get_wooCommerce_credentials()
    wcapi = WC_API(
        url="https://www.sousouus.com",
        consumer_key=wcapi_key,
        consumer_secret=wcapi_secret,
        version="v3"
    )

    productLinks = list()
    filename = sys.argv[1]
    with open(filename, 'r') as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            productLinks.append(row[0])
    pprint.PrettyPrinter(indent=4).pprint(productLinks)

    # TODO: Product Categories
    # TODO: Text translations
    for productLink in productLinks:
        print(f"Status: processing {productLink}.", file=sys.stderr)
        # Collect Product Data via webscraping
        print("\tStatus: webscraping data.", file=sys.stderr)
        html = getHTML(productLink)
        print("\tStatus: fetching product metadata.", file=sys.stderr)
        metadata = getProductMetadata(html)
        variants = metadata['product']['variants']
        # Populate data for API call
        print("\tStatus: populaing data for api call.", file=sys.stderr)
        product = dict()
        data = {'product': product}
        product['title'] = metadata['product']['name']
        product['status'] = 'draft'
        product['regular_price'] = metadata['product']['sales_price']
        product['description'] = getProductDescription(html)
        product['enable_html_description'] = True
        print("\tStatus: collecting image urls.", file=sys.stderr)
        product['images'] = getProductImages(productLink, html)
        product['in_stock'] = False
        # 'short description': '',
        # 'categories': [],
        isSimpleProduct = True if len(variants) == 1 else False
        if isSimpleProduct:
            product['type'] = constant.SIMPLE
            product['managing_stock'] = True
            product['stock_quantity'] = 0
            sku12 = "1" + metadata['product']['variants'][0]['model_number']
            sku = sku12 + calc_check_digit(sku12)
            sizeCode = sku[10:12]
            product['sku'] = sku
        else:
            product['type'] = constant.VARIABLE
            product['sku'] = metadata['product']['model_number']
            attributes = [{
                'name': 'Size',
                'slug': 'size-new',
                'variation': True,
                'visible': False,
                'options': list()
            }]
            # Add size attributes to product
            for variant in variants:
                sizeCode = variant['model_number'][-2:]
                attributes[0]['options'].append(product_sizes[sizeCode]['name'])
            product['attributes'] = attributes

            # Create a product via WooCommerce API
            variations_data = list()
            for variant in variants:
                sku12 = "1" + variant['model_number']
                sku = sku12 + calc_check_digit(sku12)
                sizeCode = sku[10:12]
                variations_data.append({
                    'sku': sku,
                    'regular_price': variant['option_price_including_tax'],
                    'managing_stock': True,
                    'stock_quantity': 0,
                    'in_stock': False,
                    'attributes': [{
                        'name': 'Size',
                        'slug': 'size-new',
                        'option': product_sizes[sizeCode]['slug']
                    }]
                })
            product['variations'] = variations_data
        # Create a product via WooCommerce API
        print("\tStatus: sending api call.", file=sys.stderr)
        response = wcapi.post("products", data)
        responseJson = response.json()
        #pprint.PrettyPrinter(indent=4).pprint(responseJson)
        print(f'\t{responseJson["product"]["title"]}')
        print(f'\t{response.status_code}: {response.ok}: Creating product')





def getProductMetadata(html):
    metadata_pattern = re.compile('\\s+var Colorme = ({.*});$', re.MULTILINE)
    metadata_matches = metadata_pattern.findall(html)
    if len(metadata_matches) > 1:
        print("Warning: Multiple matches found when expecting one json object containing product metadata. Is the data clean?", file=sys.stderr)
    elif len(metadata_matches) < 1:
        print("Fatal Error: Could not locate product metadata.", file=sys.stderr)
        exit(13)
    metadata = json.loads(metadata_matches[0])
    return metadata





def getProductDescription(html):
    # Fetch Product Description
    #soup = BeautifulSoup(page.content, 'html.parser')
    soup = BeautifulSoup(html, 'html.parser')
    productDesc = soup.find('div', class_='txt')
    if productDesc is None:
        print("Error: Could not find product description.", file=sys.stderr)
        exit(13)
    productDesc = str(productDesc)
    return productDesc





def getProductImages(productLink, html):
    pid = getProductID(productLink)
    # Grab a unique list of product images urls
    print("\tStatus: gathering image: regex.", file=sys.stderr)
    regex_pattern_product_images = re.compile(f'^.*(http.*{pid}.*jpg).*', re.MULTILINE)
    regex_matches_product_images = regex_pattern_product_images.findall(html)
    imageSet = set()
    for match in regex_matches_product_images:
        imageSet.add(match)
    # Filter out unwanted images
    print("\tStatus: gathering image: removing unwanted images.", file=sys.stderr)
    imageLinks = list()
    for imageLink in imageSet:
        http_response = requests.get(imageLink)
        bytesFile = io.BytesIO(http_response.content)
        pil_img = Image.open(bytesFile)
        width, height = pil_img.size
        # Ignore significantly wide and short images.
        # i.e. images that are captions turned jpg
        if width/height < 5:
            imageLinks.append(imageLink)
    print("\tStatus: gathering image: sort list.", file=sys.stderr)
    imageLinks.sort()
    productImages = list()
    for i in range(len(imageLinks)):
        productImages.append( { 'src': imageLinks[i], 'position': i } )
    return productImages





def getProductID(url):
    # What is the product ID, aka pid?
    regex_pattern_pid = re.compile('^http.*pid=([0-9]{9}).*', re.MULTILINE)
    regex_matches_pid = regex_pattern_pid.findall(url)
    if len(regex_matches_pid) == 0:
        print(f"Error: trouble finding a 9-digit product id from {url}.", file=sys.stderr)
        exit(13)
    elif len(regex_matches_pid) > 1:
        print(f"Warning: found more than one matches when looking for a 9-digit product id from {url}. Is the data clean?", file=sys.stderr)
    pid = regex_matches_pid[0]
    return pid





def getHTML(url):
    # Build HTTP Headers
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:70.0) Gecko/20100101 Firefox/70.0"
    headers = {'User-Agent': user_agent}
    page = requests.get(url, headers=headers)
    if page.status_code != 200:
        print(f"Error: HTTP {page.status_code}: Could not fetch page: {url}. Is the url correct?", file=sys.stderr)
        exit(13)
    html = page.content.decode(page.encoding)
    return html





def get_wooCommerce_credentials():
    # Read api key/secret
    env_path = Path('.') / '.creds'
    load_dotenv(env_path)
    wcapi_key = os.getenv('key')
    os.unsetenv('key')
    if 'key' in os.environ:
        del os.environ['key']
    wcapi_secret = os.getenv('secret')
    os.unsetenv('secret')
    if 'secret' in os.environ:
        del os.environ['secret']
    return (wcapi_key, wcapi_secret)





def calc_check_digit(number):
    """
    Calculate the EAN check digit for 13-digit numbers. The number passed
    should not have the check bit included.
    Source: https://github.com/arthurdejong/python-stdnum/blob/master/stdnum/ean.py
    """
    return str((10 - sum((3, 1)[i % 2] * int(n) for i, n in enumerate(reversed(number)))) % 10)





if __name__ == "__main__" : main()
