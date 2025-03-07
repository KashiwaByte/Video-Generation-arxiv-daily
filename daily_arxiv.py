import os
import re
import json
import arxiv
import yaml
import logging
import argparse
import datetime
import requests
import re

#
from wsgiref.handlers import format_date_time
from time import mktime
import hashlib
import base64
import hmac
from urllib.parse import urlencode
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from sparkai.llm.llm import ChatSparkLLM, ChunkPrintHandler
from sparkai.core.messages import ChatMessage , SystemMessage


FeishuAPPID = os.environ.get("APP_ID")
FeishuAPPSECRET = os.environ.get("APP_SECRET")
FeishuChatID = os.environ.get("CHATIDTEST")


XfAPPID = os.environ.get("XFAPPID")
XfAPIKEY = os.environ.get("XFAPIKEY")
XfAPISECRET = os.environ.get("XFAPISECRET")

sent_paper_num = 0



logging.basicConfig(
    format="[%(asctime)s %(levelname)s] %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)

base_url = "https://arxiv.paperswithcode.com/api/v0/papers/"
github_url = "https://api.github.com/search/repositories"
arxiv_url = "http://arxiv.org/"


def load_config(config_file: str) -> dict:
    """
    config_file: input config file path
    return: a dict of configuration
    """

    # make filters pretty
    def pretty_filters(**config) -> dict:
        keywords = dict()
        EXCAPE = '"'
        QUOTA = ""  # NO-USE
        OR = "OR"  # TODO

        def parse_filters(filters: list):
            # ret = ""
            # for idx in range(0, len(filters)):
            #     filter = filters[idx]
            #     if len(filter.split()) > 1:
            #         ret += EXCAPE + filter + EXCAPE
            #     else:
            #         ret += QUOTA + filter + QUOTA
            #     if idx != len(filters) - 1:
            #         ret += OR
            # return ret
            return filters[0]

        for k, v in config["keywords"].items():
            keywords[k] = parse_filters(v["filters"])
        return keywords

    with open(config_file, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        config["kv"] = pretty_filters(**config)
        logging.info(f"config = {config}")
    return config


def get_authors(authors, first_author=False):
    output = str()
    if first_author == False:
        output = ", ".join(str(author) for author in authors)
    else:
        output = authors[0]
    return output


def sort_papers(papers):
    output = dict()
    keys = list(papers.keys())
    keys.sort(reverse=True)
    for key in keys:
        output[key] = papers[key]
    return output


def get_code_link(qword: str) -> str:
    """
    This short function was auto-generated by ChatGPT.
    I only renamed some params and added some comments.
    @param qword: query string, eg. arxiv ids and paper titles
    @return paper_code in github: string, if not found, return None
    """
    # query = f"arxiv:{arxiv_id}"
    query = f"{qword}"
    params = {"q": query, "sort": "stars", "order": "desc"}
    r = requests.get(github_url, params=params)
    results = r.json()
    code_link = None
    if results["total_count"] > 0:
        code_link = results["items"][0]["html_url"]
    return code_link


def get_cn_abstract(text):

    APPId = os.environ.get("XFAPPID")
    APISecret =  os.environ.get("XFAPISECRET")
    APIKey = os.environ.get("XFAPIKEY")

    # 术语资源唯一标识，请根据控制台定义的RES_ID替换具体值，如不需术语可以不用传递此参数
    RES_ID = "its_en_cn_word"
    # 翻译原文本内容
    TEXT = text

    class AssembleHeaderException(Exception):
        def __init__(self, msg):
            self.message = msg

    class Url:
        def __init__(self, host, path, schema):
            self.host = host
            self.path = path
            self.schema = schema
            pass

    # calculate sha256 and encode to base64
    def sha256base64(data):
        sha256 = hashlib.sha256()
        sha256.update(data)
        digest = base64.b64encode(sha256.digest()).decode(encoding="utf-8")
        return digest

    def parse_url(requset_url):
        stidx = requset_url.index("://")
        host = requset_url[stidx + 3 :]
        schema = requset_url[: stidx + 3]
        edidx = host.index("/")
        if edidx <= 0:
            raise AssembleHeaderException("invalid request url:" + requset_url)
        path = host[edidx:]
        host = host[:edidx]
        u = Url(host, path, schema)
        return u

    # build websocket auth request url
    def assemble_ws_auth_url(requset_url, method="POST", api_key="", api_secret=""):
        u = parse_url(requset_url)
        host = u.host
        path = u.path
        now = datetime.datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        # print(date)
        # date = "Thu, 12 Dec 2019 01:57:27 GMT"
        signature_origin = "host: {}\ndate: {}\n{} {} HTTP/1.1".format(
            host, date, method, path
        )
        # print(signature_origin)
        signature_sha = hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding="utf-8")
        authorization_origin = (
            'api_key="%s", algorithm="%s", headers="%s", signature="%s"'
            % (api_key, "hmac-sha256", "host date request-line", signature_sha)
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode(
            encoding="utf-8"
        )
        # print(authorization_origin)
        values = {"host": host, "date": date, "authorization": authorization}

        return requset_url + "?" + urlencode(values)

    url = "https://itrans.xf-yun.com/v1/its"

    body = {
        "header": {"app_id": APPId, "status": 3, "res_id": RES_ID},
        "parameter": {"its": {"from": "en", "to": "cn", "result": {}}},
        "payload": {
            "input_data": {
                "encoding": "utf8",
                "status": 3,
                "text": base64.b64encode(TEXT.encode("utf-8")).decode("utf-8"),
            }
        },
    }

    request_url = assemble_ws_auth_url(url, "POST", APIKey, APISecret)

    headers = {
        "content-type": "application/json",
        "host": "itrans.xf-yun.com",
        "app_id": APPId,
    }
    # print(request_url)
    response = requests.post(request_url, data=json.dumps(body), headers=headers)
    print(headers)
    print(response)
    print(response.content)
    tempResult = json.loads(response.content.decode())
    print(
        "text字段Base64解码后=>"
        + base64.b64decode(tempResult["payload"]["result"]["text"]).decode()
    )
    cntext = json.loads(
        base64.b64decode(tempResult["payload"]["result"]["text"]).decode()
    )
    print(cntext["trans_result"]["dst"])

    return cntext["trans_result"]["dst"]

def get_summarize_abstract(text):
    
    APPId = os.environ.get("XFAPPID")
    APISecret =  os.environ.get("XFAPISECRET")
    APIKey = os.environ.get("XFAPIKEY")
    
    #星火认知大模型Spark Max的URL值，其他版本大模型URL值请前往文档（https://www.xfyun.cn/doc/spark/Web.html）查看
    SPARKAI_URL = 'wss://spark-api.xf-yun.com/v4.0/chat'
    #星火认知大模型调用秘钥信息，请前往讯飞开放平台控制台（https://console.xfyun.cn/services/bm35）查看
    SPARKAI_APP_ID = APPId
    SPARKAI_API_SECRET = APISecret
    SPARKAI_API_KEY = APIKey
    #星火认知大模型Spark Max的domain值，其他版本大模型domain值请前往文档（https://www.xfyun.cn/doc/spark/Web.html）查看
    SPARKAI_DOMAIN = '4.0Ultra'
    
    spark = ChatSparkLLM(
        spark_api_url=SPARKAI_URL,
        spark_app_id=SPARKAI_APP_ID,
        spark_api_key=SPARKAI_API_KEY,
        spark_api_secret=SPARKAI_API_SECRET,
        spark_llm_domain=SPARKAI_DOMAIN,
        streaming=False,
    )

    messages = [SystemMessage(role = "system" , content="""你是一个学术论文摘要的解析大师，你会接受到学术论文的摘要，理解后解析为如下两个部分1.解决了什么问题。2.有什么创新亮点。严格参照以下示例 :
                            一.问题解决
                            本文主要解决了超高分辨率（Uhr）遥感图像（RSI）在当前遥感多模态大型语言模型（RSMLLM）中处理困难的问题。具体而言，UhrRSI的大量空间和上下文信息难以被标准RSMLLM处理，因为这些图像要么需要调整大小以适应标准输入尺寸从而丢失重要信息，要么其原始大小超出令牌限制，使得捕捉长程依赖关系和基于丰富视觉上下文回答问题变得困难。
                            二.创新亮点
                            1.无需训练框架：介绍了ImageRag for RS，这是一个无需额外训练的框架，专门用于分析Uhr RSI。
                            2.基于检索增强生成（RAG）技术的机制：设计了一种新颖的图像上下文检索机制（ImageRag），通过将Uhr RSI分析任务转化为图像的长上下文选择任务，能够高效地选择性检索和关注与给定查询最相关的图像部分。
                            3.双路径处理：提出了快速路径和慢速路径两种方法来高效处理Uhr RSI，确保既能准确又能高效地管理大量上下文和空间信息。"""), 

       ChatMessage(role = "user", content = text ) ]
   
    handler = ChunkPrintHandler()
    a = spark.generate([messages], callbacks=[handler])
    print(a.generations[0][0].message.content)
    raw_ans = a.generations[0][0].message.content
    html_text = raw_ans.replace('\n', '<br>')
    return f"<p>{html_text}</p>"


def sent_to_feishu(update_time, paper_title, paper_url, repo_url, paper_abstract):
    FeishuAPPID = os.environ.get("APP_ID")
    FeishuAPPSECRET = os.environ.get("APP_SECRET")
    FeishuChatID = os.environ.get("CHATIDTEST")
   
    paper_title = paper_title  # 替换为你的标题
    update_time = update_time  # 替换为你的更新时间
    paper_abstract = paper_abstract  # 替换为你的摘要
    paper_url = paper_url  # 替换为你的论文链接
    repo_url =  repo_url  # 替换为你的代码链接


    # 创建client
    client = (
        lark.Client.builder()
        .app_id(FeishuAPPID)
        .app_secret(FeishuAPPSECRET)
        .log_level(lark.LogLevel.DEBUG)
        .build()
    )
    


    # 输入变量
    data = {
        "type": "template",
        "data": {
            "template_id": "AAqjsoNXDu0sU",
            "template_variable": {
                "paper_title": paper_title,
                "update_time": str(update_time),
                "abstract": paper_abstract,
                "paper_url": paper_url,
                "repo_url": repo_url,
            },
        },
    }

    content = json.dumps(data, ensure_ascii=False)  # ensure_ascii=False 保证中文不会被转义

    # 构造请求对象
    request: CreateMessageRequest = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(FeishuChatID)
            .msg_type("interactive")
            .content(
                content
            )
            .build()
        )
        .build()
    )

    # 发起请求
    response: CreateMessageResponse = client.im.v1.message.create(request)

    # 处理失败返回
    if not response.success():
        lark.logger.error(
            f"client.im.v1.message.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}, resp: \n{json.dumps(json.loads(response.raw.content), indent=4, ensure_ascii=False)}"
        )
        return

    # 处理业务结果
    lark.logger.info(lark.JSON.marshal(response.data, indent=4))


def check_update_time(update_time_str):
    """
    Checks if update_time is yesterday's date.

    Args:
        update_time_str: The update time as a string (YYYY-MM-DD).

    Returns:
        True if update_time is yesterday, False otherwise.  Returns None if the date string is invalid.
    """
    try:
        update_time = datetime.datetime.strptime(update_time_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"Invalid date format: {update_time_str}")
        return None

    yesterday = datetime.date.today() - datetime.timedelta(days=180)
    return update_time == yesterday


def get_daily_papers(topic, query="agent", max_results=2):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """
    # output
    content = dict()
    content_to_web = dict()
    print("-----------------")
    print(f"query is {query}")
    print("-----------------")
    search_engine = arxiv.Search(
        query= query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    
    global sent_paper_num

    for result in search_engine.results():
        # 定义正则表达式
        pattern = r"(?i)\b(AAAI|NeurIPS|ACL|CVPR|ICCV|ICML|IJCAI|EMNLP|COLING|NAACL|EACL|CoNLL|ICLR|INLG|ECCV|MICCAI|IROS|MIDL|ICIP|KDD|MIDC)(?:\s?(\d{4}))?\b"

        paper_id = result.get_short_id()
        paper_title = result.title

        paper_url = result.entry_id
        code_url = base_url + paper_id  # TODO

        paper_abstract = result.summary.replace("\n", " ")
        paper_abstract = paper_abstract.replace("|", ",")
        paper_abstract = paper_abstract.replace("\n", " ")

        paper_authors = get_authors(result.authors)
        paper_first_author = get_authors(result.authors, first_author=True)
        primary_category = result.primary_category
        publish_time = result.published.date()
        update_time = result.updated.date()
        comments = result.comment
        if comments == None:
            comments = "null"
        matches = re.findall(pattern, comments)
        if matches:
            # 格式化输出匹配结果
            formatted_matches = [f"{conf} {year}".strip() for conf, year in matches]
            paper_comment = ", ".join(formatted_matches)
        else:
            paper_comment = "null"

        logging.info(
            f"Time = {update_time} title = {paper_title} author = {paper_first_author}"
        )

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find("v")
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos]
        paper_url = arxiv_url + "abs/" + paper_key

        try:
            # source code link
            r = requests.get(code_url).json()
            repo_url = None
            if "official" in r and r["official"]:
                repo_url = r["official"]["url"]

            if repo_url is not None:
                content[paper_key] = (
                    "|**{}**|**[{}]({})**|**{}**|**[link]({})**|**{}**|\n".format(
                        update_time,
                        paper_title,
                        paper_url,
                        paper_comment,
                        repo_url,
                        paper_abstract,
                    )
                )
                content_to_web[paper_key] = (
                    "- {}, **{}**, Paper: [{}]({}), Code: **[{}]({})**".format(
                        update_time,
                        paper_title,
                        paper_url,
                        paper_url,
                        repo_url,
                        repo_url,
                    )
                )

            else:
                pass
                # content[paper_key] = "|**{}**|**[{}]({})**|**{}**|null|{}|\n".format(
                #     update_time, paper_title, paper_url, paper_comment, paper_abstract
                # )
                # content_to_web[paper_key] = "- {}, **{}**, Paper: [{}]({}),{}".format(
                #     update_time, paper_title, paper_url, paper_url, paper_abstract
                # )

            # 如果是昨天的paper则推送到飞书
            if check_update_time(str(update_time))  and repo_url is not None:
                cnabstract = get_cn_abstract(paper_abstract)
                summarize_abstract = get_summarize_abstract(cnabstract)

            # TODO: select useful comments
            comments = None
            if comments != None:
                content_to_web[paper_key] += f", {comments}\n"
            else:
                content_to_web[paper_key] += f"\n"

        except Exception as e:
            logging.error(f"exception: {e} with id: {paper_key}")

    data = {topic: content}
    data_web = {topic: content_to_web}
    return data, data_web


def update_paper_links(filename):
    """
    weekly update paper links in json file
    """

    def parse_arxiv_string(s):
        parts = s.split("|")
        date = parts[1].strip()
        title = parts[2].strip()
        # authors = parts[3].strip()
        arxiv_id = parts[4].strip()
        code = parts[5].strip()
        paper_abstract = parts[6].strip()
        arxiv_id = re.sub(r"v\d+", "", arxiv_id)
        return date, title, arxiv_id, code, paper_abstract

    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

        json_data = m.copy()

        for keywords, v in json_data.items():
            logging.info(f"keywords = {keywords}")
            for paper_id, contents in v.items():
                contents = str(contents)

                update_time, paper_title, paper_url, code_url, paper_abstract = (
                    parse_arxiv_string(contents)
                )

                contents = "|{}|{}|{}|{}|{}|\n".format(
                    update_time, paper_title, paper_url, code_url, paper_abstract
                )
                json_data[keywords][paper_id] = str(contents)
                logging.info(
                    f"paper_id = {paper_id}, contents = {contents} ,paper_abstract = {paper_abstract}"
                )

                valid_link = False if "|null|" in contents else True
                if valid_link:
                    continue
                try:
                    code_url = base_url + paper_id  # TODO
                    r = requests.get(code_url).json()
                    repo_url = None
                    if "official" in r and r["official"]:
                        repo_url = r["official"]["url"]
                        if repo_url is not None:
                            new_cont = contents.replace(
                                "|null|", f"|**[link]({repo_url})**|"
                            )
                            logging.info(f"ID = {paper_id}, contents = {new_cont}")
                            json_data[keywords][paper_id] = str(new_cont)

                except Exception as e:
                    logging.error(f"exception: {e} with id: {paper_id}")
        # dump to json file
        print(json_data)
        with open(filename, "w") as f:
            json.dump(json_data, f)


def update_json_file(filename, data_dict):
    """
    daily update json file using data_dict
    """
    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

    json_data = m.copy()

    # update papers in each keywords
    for data in data_dict:
        for keyword in data.keys():
            papers = data[keyword]

            if keyword in json_data.keys():
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename, "w") as f:
        json.dump(json_data, f)


def json_to_md(
    filename,
    md_filename,
    task="",
    to_web=False,
    use_title=True,
    use_tc=True,
    show_badge=True,
    use_b2t=True,
):
    """
    @param filename: str
    @param md_filename: str
    @return None
    """

    def pretty_math(s: str) -> str:
        ret = ""
        match = re.search(r"\$.*\$", s)
        if match == None:
            return s
        math_start, math_end = match.span()
        space_trail = space_leading = ""
        if s[:math_start][-1] != " " and "*" != s[:math_start][-1]:
            space_trail = " "
        if s[math_end:][0] != " " and "*" != s[math_end:][0]:
            space_leading = " "
        ret += s[:math_start]
        ret += f"{space_trail}${match.group()[1:-1].strip()}${space_leading}"
        ret += s[math_end:]
        return ret

    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace("-", ".")

    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()
        if not content:
            data = {}
        else:
            data = json.loads(content)

    # clean README.md if daily already exist else create it
    with open(md_filename, "w+", encoding="utf-8") as f:
        pass

    # write data into README.md
    with open(md_filename, "a+", encoding="utf-8") as f:

        if (use_title == True) and (to_web == True):
            f.write("---\n" + "layout: default\n" + "---\n\n")

        if show_badge == True:
            pass

        if use_title == True:
            # f.write(("<p align="center"><h1 align="center"><br><ins>CV-ARXIV-DAILY"
            #         "</ins><br>Automatically Update CV Papers Daily</h1></p>\n"))
            f.write("## Updated on " + DateNow + "\n")
        else:
            f.write("> Updated on " + DateNow + "\n")

        # TODO: add usage
        f.write("> Usage instructions: [here](./docs/README.md#usage)\n\n")

        # Add: table of contents
        if use_tc == True:
            f.write("<details>\n")
            f.write("  <summary>Table of Contents</summary>\n")
            f.write("  <ol>\n")
            for keyword in data.keys():
                day_content = data[keyword]
                if not day_content:
                    continue
                kw = keyword.replace(" ", "-")
                f.write(f"    <li><a href=#{kw.lower()}>{keyword}</a></li>\n")
            f.write("  </ol>\n")
            f.write("</details>\n\n")

        for keyword in data.keys():
            day_content = data[keyword]
            if not day_content:
                continue
            # the head of each part
            f.write(f"## {keyword}\n\n")

            if use_title == True:
                if to_web == False:
                    f.write(
                        "|Publish Date|Title|Accepted|Code|abstract|\n"
                        + "|---|---|---|---|---|\n"
                    )

            # sort papers by date
            day_content = sort_papers(day_content)

            for _, v in day_content.items():
                if v is not None:
                    f.write(pretty_math(v))  # make latex pretty

            f.write(f"\n")

            # Add: back to top
            if use_b2t:
                top_info = f"#Updated on {DateNow}"
                top_info = top_info.replace(" ", "-").replace(".", "")
                f.write(
                    f"<p align=right>(<a href={top_info.lower()}>back to top</a>)</p>\n\n"
                )

        if show_badge == True:
            # we don't like long string, break it!
            pass

    logging.info(f"{task} finished")


def demo(**config):
    # TODO: use config
    data_collector = []
    data_collector_web = []

    keywords = config["kv"]
    max_results = config["max_results"]
    publish_readme = config["publish_readme"]
    show_badge = config["show_badge"]

    b_update = config["update_paper_links"]
    logging.info(f"Update Paper Link = {b_update}")
    if config["update_paper_links"] == False:
        logging.info(f"GET daily papers begin")
        for topic, keyword in keywords.items():
            print(keyword)
            print("=========================")
            logging.info(f"Keyword: {topic}")
            data, data_web = get_daily_papers(
                topic, query=keyword, max_results=max_results
            )
            data_collector.append(data)
            data_collector_web.append(data_web)
            print("\n")
        logging.info(f"GET daily papers end")

    # 1. update README.md file
    if publish_readme:
        json_file = config["json_readme_path"]
        md_file = config["md_readme_path"]
        # update paper links
        if config["update_paper_links"]:
            update_paper_links(json_file)
        else:
            # update json data
            update_json_file(json_file, data_collector)
        # json data to markdown
        json_to_md(json_file, md_file, task="Update Readme", show_badge=show_badge)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config_path", type=str, default="config.yaml", help="configuration file path"
    )
    parser.add_argument(
        "--update_paper_links",
        default=False,
        action="store_true",
        help="whether to update paper links etc.",
    )
    args = parser.parse_args()
    config = load_config(args.config_path)
    config = {**config, "update_paper_links": args.update_paper_links}
    demo(**config)
