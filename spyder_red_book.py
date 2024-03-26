# --coding:utf-8--
import os
import time
import pandas as pd
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import csv
import urllib.request
from urllib.parse import urljoin
from tqdm import tqdm  # 引入tqdm库
import random
from datetime import datetime


def initialize_webdriver():
    options = Options()
    # 设置用户代理字符串
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
    options.add_argument(f'user-agent={user_agent}')
    # options.add_argument("--headless")    ##是否能看到

    # 初始化WebDriver，确保指定chromedriver的路径，如果已经配置环境变量，则不需要
    driver = webdriver.Chrome(options=options)
    with open('stealth.min.js') as f:
        js = f.read()

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": js
    })

    return driver


# ----------------抓博主信息---------------

def download_user_avatar(driver, save_path):
    # 找到头像图片的URL
    avatar_url = driver.find_element(By.CSS_SELECTOR, ".avatar img").get_attribute("src")
    # 使用urllib下载图片
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    urllib.request.urlretrieve(avatar_url, save_path + '/avatar.jpg')


def fetch_user_info_and_save_to_csv(driver, initial_url):
    # 抓取数据
    driver.get(initial_url)
    time.sleep(30)
    user_name = driver.find_element(By.CSS_SELECTOR, ".user-nickname .user-name").text
    user_info = driver.find_element(By.CSS_SELECTOR, ".user-content").text.split('\n')
    red_id = user_info[0].split("：")[1]
    ip_location = user_info[1].split("：")[1]
    user_desc = driver.find_element(By.CSS_SELECTOR, ".user-desc").text
    tags_elements = driver.find_elements(By.CSS_SELECTOR, ".user-tags .tag-item div")
    tags = [tag.text for tag in tags_elements if tag.text != '']
    tags_str = '、'.join(tags)
    data_info = driver.find_elements(By.CSS_SELECTOR, ".data-info .user-interactions div")
    follows = data_info[0].text.split("\n")[0]
    followers = data_info[1].text.split("\n")[0]
    likes_and_favorites = data_info[2].text.split("\n")[0]
    # 将数据存入列表
    data = [user_name, red_id, ip_location, user_desc, tags_str, follows, followers, likes_and_favorites]
    # 写入CSV
    header = ["博主名", "小红书号", "IP属地", "简介", "博主标签", "关注数", "粉丝数", "获赞与收藏数"]
    filepath = f'{user_name}/A-博主介绍'
    download_user_avatar(driver, filepath)
    with open(filepath + '/bloggers_info.csv', mode='a', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerow(data)
    print("完成博主信息抓取")
    return user_name


# ----------------抓博文信息---------------

def get_media_urls(driver):
    video_elements = driver.find_elements(By.CSS_SELECTOR, '.player-container video')
    if video_elements:
        video_urls = [video.get_attribute('src') for video in video_elements]
        return ('video', video_urls)
    else:
        image_elements = driver.find_elements(By.CSS_SELECTOR, '.swiper-slide')
        image_urls = [el.get_attribute('style').split('"')[1] for el in image_elements if
                      'background-image' in el.get_attribute('style')]
        return ('image', list(set(image_urls)))


def download_media(media_type, media_urls, save_dir):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    for i, url in enumerate(media_urls):
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                file_extension = 'mp4' if media_type == 'video' else 'webp'
                file_path = os.path.join(save_dir, f'{media_type}_{i}.{file_extension}')
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
        except Exception as e:
            print(f"An error occurred while downloading {url}: {e}")


def scrape_xiaohongshu_post(driver, url, image_save_path):
    driver.get(url)
    media_type, media_urls = get_media_urls(driver)
    download_media(media_type, media_urls, image_save_path)

    post_data = {}
    elements_selectors = {
        'author': ('.info .name .username', 'text'),
        'title': ('#detail-title', 'text'),
        'content': ('#detail-desc', 'text'),
        'topics': ('#hash-tag', 'text_multiple'),
        'date_location': ('.bottom-container .date', 'text'),
        'likes': ('.like-wrapper .count', 'text'),
        'collects': ('.collect-wrapper .count', 'text'),
        'comments': ('.chat-wrapper .count', 'text'),
    }

    for key, (selector, attr) in elements_selectors.items():
        try:
            if attr == 'text_multiple':
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                post_data[key] = ' '.join([element.text for element in elements])
            else:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                post_data[key] = element.text if attr == 'text' else element.get_attribute(attr)
        except NoSuchElementException:
            post_data[key] = '' if key != 'date_location' else ('', '')

    if post_data['date_location']:
        try:
            date, location = post_data['date_location'].split(' ')
        except:
            date, location = post_data['date_location'], ''

        del post_data['date_location']
        post_data['date'] = date
        post_data['location'] = location

    df = pd.DataFrame([post_data])
    return df


def get_all_post_urls(driver, base_url):
    post_urls = set()
    last_post_id = None

    while True:
        # 获取当前页面所有博文的容器
        posts = driver.find_elements_by_css_selector("section.note-item")
        for post in posts:
            # 根据给定的HTML结构，选择非隐藏的<a>标签
            link = post.find_element_by_css_selector("a:not([style*='display: none;'])")
            url = link.get_attribute("href")
            full_url = urljoin(base_url, url)
            post_urls.add(full_url)
        new_last_post_id = posts[-1].get_attribute("data-index")

        # 检查最后一个博文的索引是否变化，若未变化则认为所有博文已加载完毕
        if new_last_post_id == last_post_id:
            print("所有博文已加载完毕")
            break
        else:
            last_post_id = new_last_post_id
            # 滚动到页面底部以加载新的博文
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # 等待新博文加载
            time.sleep(random.randint(1, 3))

    return list(post_urls)


def scrape_post_details(driver, post_urls, result_path, limitdate1, limitdate2):
    all_posts_info = []
    for url in tqdm(post_urls, desc='Processing posts'):  # 使用tqdm包装你的循环，并添加描述
        driver.get(url)
        time.sleep(random.randint(1, 3))  # 调整等待时间以确保页面加载完成
        time_and_location = driver.find_element_by_css_selector('.bottom-container .date').text.split(' ')
        date_str = time_and_location[0]
        # 将字符串转换为datetime对象
        date = datetime.strptime(date_str, "%Y-%m-%d")

        # 判断日期关系
        is_between = limitdate1 <= date <= limitdate2
        if not is_between:
            continue

        title = driver.find_element_by_css_selector('#detail-title').text
        # 构造文件名时替换掉标题中不适合文件名的字符
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c == ' ']).rstrip()

        # 调用你的爬取博文详细信息的函数
        post_info = scrape_xiaohongshu_post(driver, url, f'{result_path}/{date_str}_{safe_title}/')
        all_posts_info.append(post_info)

        all_post_details = pd.concat(all_posts_info, ignore_index=True)
        all_post_details.to_csv(f"{result_path}/All_post_details.csv", index=False, encoding='utf-8-sig')


# 在这里进行你的博文数据提取逻辑


driver = initialize_webdriver()
bolggers_list = ['https://www.xiaohongshu.com/user/profile/6146922800000000020182f9',
                 "https://www.xiaohongshu.com/user/profile/5aad0ad84eacab0e81b85bfa", ]
limitdate1_list = ['2021-02-15', '2024-01-24']
limitdate2_list = ['2024-04-15', '2024-03-25']
for initial_url, limitdate1_str, limitdate2_str in zip(bolggers_list, limitdate1_list, limitdate2_list):
    limitdate1 = datetime.strptime(limitdate1_str, "%Y-%m-%d")
    limitdate2 = datetime.strptime(limitdate2_str, "%Y-%m-%d")
    name = fetch_user_info_and_save_to_csv(driver, initial_url)
    result_path = f'{name}/'
    post_urls = get_all_post_urls(driver, 'https://www.xiaohongshu.com')
    print(post_urls)

    scrape_post_details(driver, post_urls, result_path,limitdate1,limitdate2)
driver.quit()
