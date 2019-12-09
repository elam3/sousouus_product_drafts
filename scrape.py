import requests
import sys
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pathlib import Path
import os
from woocommerce import API
import re
import json
import constant
from PIL import Image
import io

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

    # Build HTTP Headers
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:70.0) Gecko/20100101 Firefox/70.0"
    headers = {'User-Agent': user_agent}

    # TODO: Scale the URL input
    # Web scraping for product HTML page
    url = "https://www.sousou.co.jp/?pid=147050452"
    page = requests.get(url, headers=headers)
    if page.status_code != 200:
        print(f"Error: HTTP {page.status_code}: Could not fetch page: {url}. Is the url correct?", file=sys.stderr)
        exit(13)

    html = page.content.decode(page.encoding)

    # What is the product ID, aka pid?
    regex_pattern_pid = re.compile('^http.*pid=([0-9]{9}).*', re.MULTILINE)
    regex_matches_pid = regex_pattern_pid.findall(url)
    if len(regex_matches_pid) == 0:
        print(f"Error: trouble finding a 9-digit product id from {url}.", file=sys.stderr)
        exit(13)
    elif len(regex_matches_pid) > 1:
        print(f"Warning: found more than one matches when looking for a 9-digit product id from {url}. Is the data clean?", file=sys.stderr)
    pid = regex_matches_pid[0]

    # Grab a unique list of product images urls
    regex_pattern_product_images = re.compile(f'^.*(http.*{pid}.*jpg).*', re.MULTILINE)
    regex_matches_product_images = regex_pattern_product_images.findall(html)
    imageSet = set()
    for match in regex_matches_product_images:
        imageSet.add(match)

    # Filter out unwanted images
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


    # TODO: Size Attributes
    # TODO: Product Categories
    # TODO: Text translations


    # Fetch Product Description
    soup = BeautifulSoup(page.content, 'html.parser')
    productDesc = soup.find('div', class_='txt')
    if productDesc is None:
        print("Error: Could not find product description.", file=sys.stderr)
        exit(13)
    else:
        productDesc = productDesc[0]


    # Grab product metadata; e.g. product_code, price, etc.
    metadata_pattern = re.compile('\\s+var Colorme = ({.*});$', re.MULTILINE)
    metadata_matches = metadata_pattern.findall(html)
    if len(metadata_matches) > 1:
        print("Warning: Multiple matches found when expecting one json object containing product metadata. Is the data clean?", file=sys.stderr)
    elif len(metadata_matches < 1):
        print("Fatal Error: Could not locate product metadata.", file=sys.stderr)
        exit(13)
    metadata = json.loads(metadata_matches[0])
    productTitle = metadata['product']['name']
    productCode = metadata['product']['model_number']
    variants = metadata['product']['variants']
    productType = ""
    if len(variants) == 1: # e.g. simple product
        productType = constant.SIMPLE
    else: # e.g. variable product
        productType = constant.VARIABLE
        productChildren = list()
        for variant in variants:
            child = dict()
            sku12 = "1" + variant['model_number']
            sku = sku12 + calc_check_digit(sku12)
            child['sku'] = sku
            child['regular_price'] = str(variant['option_price'])
            sizeCode = sku[10:12]
            #TODO: attribute code?
            #child['attributes'] = []
            child['managing_stock'] = True
            child['stock_quantity'] = 0
            child['in_stock'] = False
            productChildren.append(child)

    # Create a product via WooCommerce API
    wcapi = API(
        url="https://www.sousouus.com",
        consumer_key=wcapi_key,
        consumer_secret=wcapi_secret,
        version="v3"
    )
    data = {
	"product": {
	    "title": productTitle,
	    "type": productType,
            "sku": productCode,
	    "regular_price": productPrice,
	    "description":  productDesc,
            "variations": productChildren
	}
    }
    response = wcapi.post("products", data).json()





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
