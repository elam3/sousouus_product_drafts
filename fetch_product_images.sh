#!/bin/bash
WP_POST_ID="$2" # e.g. 125867
COLORME_PROD_LINK="$1" # e.g. https://www.sousou.co.jp/?pid=147050452
COLORME_PROD_ID=`echo "${COLORME_PROD_LINK}" | perl -pe 's|^(http.*pid=)([0-9]+)|\2|'`

# Get product page
USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:70.0) Gecko/20100101 Firefox/70.0"
TMPFILE="/tmp/${$}-${COLORME_PROD_ID}-`date +%s`"
curl --user-agent "${USER_AGENT}" "${COLORME_PROD_LINK}" --output "${TMPFILE}";

# List product images, and send to wordpress via wp-cli.
# e.g. https://img05.shop-pro.jp/PA01018/434/product/147050452.jpg
while IFS='' read -r line; do
    # Ignore the image that's 8x wider than tall. (i.e. the image with jpn text)
    php -r "\$arr = getimagesize('${line}'); if(\$arr[0]/\$arr[1]>8){exit(0);}else{exit(1);}" &>/dev/null
    [ $? -eq 0 ] && \
        wp --path=/public_html media import $line --post_id=${WP_POST_ID}
done < <(grep -E "${COLORME_PROD_ID}.*\.jpg" "${TMPFILE}" | perl -pe "s|^.*(http.*${COLORME_PROD_ID}.*jpg).*|\1|" | sort | uniq)

rm -f "${TMPFILE}"
