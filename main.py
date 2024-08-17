import re, aiohttp, json, time, textwrap

from util.plugin_dev.api.v1.bot import Context, AstrMessageEvent, CommandResult
from util.plugin_dev.api.v1.config import *

DATA_PATH = "data/astrbot_plugin_fund_data.json"

class Main:
    def __init__(self, context: Context) -> None:
        NAMESPACE = "astrbot_plugin_fund"
        self.context = context
        self.context.register_commands(NAMESPACE, "基金", "查看基金", 1, self.fund_view)
        self.context.register_commands(NAMESPACE, "添加基金", "添加持有的基金", 10, self.fund_add)
        self.context.register_commands(NAMESPACE, "持仓", "查看持仓", 0, self.personal_fund)
        
        if not os.path.exists(DATA_PATH):
            with open(DATA_PATH, "w") as f:
                f.write("{}")
        with open(DATA_PATH, "r") as f:
            self.data = json.load(f) # unified_id -> {fundCode -> [[fundAmount, last_update_ts_sec], ...]}

    async def fund_view(self, message: AstrMessageEvent, context: Context):
        l = message.message_str.split(" ")
        if len(l) != 2 or not l[1].isdigit():
            return CommandResult().message("参数错误").use_t2i(False)
        fundCode = l[1]

        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://fund.eastmoney.com/pingzhongdata/{fundCode}.js") as response:
                res = await response.text()
                name = re.findall("var fS_name = \"(.*?)\";", res)[0]
                interest_3_mon = re.findall("var syl_3y=\"(.*?)\";", res)[0]
                interest_1_mon = re.findall("var syl_1y=\"(.*?)\";", res)[0]
                interest_a_yr = re.findall("var syl_1n=\"(.*?)\";", res)[0]
                
                ret = textwrap.dedent(f"""
                    基金名称：{name} ({fundCode})
                    近三月收益率：{interest_3_mon}%
                    近一年收益率：{interest_1_mon}%
                    年化收益率：{interest_a_yr}%
                    """).strip()
                return CommandResult().message(ret).use_t2i(False)
    
    async def fund_add(self, message: AstrMessageEvent, context: Context):
        l = message.message_str.split(" ")
        if len(l) != 3 or not l[1].isdigit() or not l[2].replace(".", "", 1).isdigit():
            return CommandResult().message("输入 `添加基金 <基金id> <持有份额>` 以添加监控。").use_t2i(False)
        fundCode = l[1]
        fundAmount = float(l[2])
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://fund.eastmoney.com/pingzhongdata/{fundCode}.js") as response:
                res = await response.text()
                name = re.findall("var fS_name = \"(.*?)\";", res)[0]
                trend_ = re.findall("var Data_netWorthTrend = (\[{.*?}\]);/\*累计净值走势", res)[0]
                net_worth_latest = float(json.loads(trend_)[-1]['y'])
                
                total_finance = net_worth_latest * fundAmount
                
                if str(message.message_obj.sender.user_id) in self.data:
                    if fundCode in self.data[str(message.message_obj.sender.user_id)]:
                        self.data[str(message.message_obj.sender.user_id)][fundCode].append([fundAmount, int(time.time())])
                    else:
                        self.data[str(message.message_obj.sender.user_id)][fundCode] = [[fundAmount, int(time.time())]]
                else:
                    self.data[str(message.message_obj.sender.user_id)] = {fundCode: [[fundAmount, int(time.time())]]}

                await self._save_data()
                
                return CommandResult().message(f"已添加基金：{name}\n你输入的持有份额：{fundAmount}\n最新净值：{net_worth_latest}\n因此，持有金额为：{total_finance:.2f}").use_t2i(False)

    async def _save_data(self):
        with open(DATA_PATH, "w") as f:
            json.dump(self.data, f)
                
    async def personal_fund(self, message: AstrMessageEvent, context: Context):
        if str(message.message_obj.sender.user_id) not in self.data:
            return CommandResult().message("你还没有添加任何基金。").use_t2i(False)
        
        ret = ""
        personal_finance = 0
        interest_change = 0
        for fundCode, fundAmounts in self.data[str(message.message_obj.sender.user_id)].items():
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://fund.eastmoney.com/pingzhongdata/{fundCode}.js") as response:
                    res = await response.text()
                    name = re.findall("var fS_name = \"(.*?)\";", res)[0]
                    trend_ = re.findall("var Data_netWorthTrend = (\[{.*?}\]);/\*累计净值走势", res)[0]
                    net_worth_latest = float(json.loads(trend_)[-1]['y'])
                    net_worth_yesterday = float(json.loads(trend_)[-2]['y'])
                    
                    fund_amount = fundAmounts[-1][0]
                    total_finance = net_worth_latest * fund_amount
                    total_finance_yesterday = net_worth_yesterday * fund_amount
                    interest = total_finance - total_finance_yesterday
                    ret += textwrap.dedent(f"""
                        -
                        基金名称：{name} ({fundCode})
                        持有份额：{sum([fundAmount for fundAmount, _ in fundAmounts])}
                        持有金额：{total_finance:.2f}
                        今日收益：{interest:.2f}
                        """).strip() + "\n"

                    personal_finance += total_finance
                    interest_change += interest
                    
        ret += f"====\n名下基金总资产: {personal_finance:.2f}\n今日收益: {interest_change:.2f}"
        
        return CommandResult().message(ret).use_t2i(False)
    