import useragents
import requests
from requests.exceptions import ConnectionError
from urllib.parse import urlencode
from pyquery import PyQuery as pq
import pymongo


client = pymongo.MongoClient('localhost')
wxartical = client.wxartical
wxcollection = wxartical.wxcollection

KEY_WORDS = "风景"
URL_BASE = "http://weixin.sogou.com/weixin?"
proxy_url = 'http://0.0.0.0:5555/random'
proxy_global = None
count_request = 0
count_change_proxy = 0


def get_proxy():
    try:
        response_proxy = requests.get(proxy_url)
        if response_proxy.status_code == 200:
            return response_proxy.text
        return None
    except Exception as e:
        # 代理获取失败 重新获取代理
        print('获取代理失败', e.reason)
        get_proxy()


def get_page(offset):
    params = {
        'query': KEY_WORDS,
        's_from': 'input',
        'type': '2',
        'ie': 'utf8',
        'page': offset
    }
    param = urlencode(params)
    url = URL_BASE + param
    print("这是第%s页，对应的链接是%s" % (str(offset), url))
    return get_page_html(url)


def get_page_html(url):
    global proxy_global
    global count_request
    global count_change_proxy

    # 如果已经达到了最大的错误请求次数，直接退出  防止死循环
    if count_request == 10:
        print("错误次数已达上限")
        return None
    if count_change_proxy == 100:
        print("已从数据库中获取到了100个代理，建议停止使用")
        return None

    try:
        print("正在使用代理：", proxy_global)
        if proxy_global:
            proxies = {
                'http': 'http://' + proxy_global,
                'https': 'https://' + proxy_global
            }
            response = requests.get(url, allow_redirects=False, headers=useragents.get_user_agent(), proxies=proxies)
        else:
            response = requests.get(url, allow_redirects=False, headers=useragents.get_user_agent())

        if response.status_code == 200:
            return response.text
        if response.status_code == 302:
            # 被ban掉以后  重新发起请求  更换代理
            proxy_global = get_proxy()
            if proxy_global:
                print("又从数据库中获取了一个新的代理：%s, 这是第%s次获取代理" % (proxy_global, count_change_proxy))
                count_change_proxy += 1
                return get_page_html(url)
            else:
                print("获取代理失败了，有可能是没有可用代理了")
                return None
    except ConnectionError as e:
        print("错误原因", e.reason)
        # 错误 重新发起请求 更换一次代理
        proxy_global = get_proxy()
        get_page_html(url)
        # 请求错误的次数
        count_request += 1


def parse_page(html):
    doc = pq(html)
    items = doc('.txt-box h3 a').items()
    for item in items:
        yield item.attr('href')


def get_detail(html):
    try:
        response = requests.get(html)
        if response.status_code == 200:
            return response.text
        return None
    except ConnectionError as e:
        print(e.reason)
        return None


def parse_detail(html, url):
    doc = pq(html)
    title = doc('.rich_media_title').text()
    content = doc('.rich_media_content ').text()
    date = doc('.rich_media_meta rich_media_meta_nickname #publish_time').text()
    yield {
        'title': title,
        'content': content,
        'date': date,
        'url': url
    }


def save_to_mongo(result):
    if wxcollection.update({'title': result['title']}, {'$set': result}, True):
        print("插入成功")
    else:
        print("插入失败")


def main(offset):
    html = get_page(offset)
    # 解析
    for item in parse_page(html):
        html_detail = get_detail(item)
        results = parse_detail(html_detail, item)
        for result in results:
            if result:
                save_to_mongo(result)


if __name__ == '__main__':
    for i in range(0, 100):
        main(i)