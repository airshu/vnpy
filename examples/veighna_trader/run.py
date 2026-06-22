from vnpy.event import EventEngine

from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

from vnpy_ctp import CtpGateway                        # CTP期货交易接口（上海期货信息技术）
# from vnpy_ctptest import CtptestGateway              # CTP穿透式测试接口（期货公司合规测试用）
# from vnpy_mini import MiniGateway                    # 中金所迷你股指期货接口
# from vnpy_femas import FemasGateway                  # 飞马期货交易接口（飞创信息技术）
# from vnpy_sopt import SoptGateway                    # 上证股票期权接口
# from vnpy_esunny import EsunnyGateway                # 易盛国际期货交易接口
# from vnpy_xtp import XtpGateway                      # 中泰XTP证券交易接口
# from vnpy_tora import ToraStockGateway, ToraOptionGateway  # 华鑫奇点股票/期权接口
# from vnpy_ib import IbGateway                        # 盈透证券（Interactive Brokers）接口
# from vnpy_tap import TapGateway                      # 易盛Tap国际期货接口
# from vnpy_da import DaGateway                        # 直达国际期货接口
# from vnpy_rohon import RohonGateway                  # 融航资管系统接口
# from vnpy_tts import TtsGateway                      # TTS仿真交易接口

from vnpy_paperaccount import PaperAccountApp        # 模拟交易账户（无需实盘即可模拟下单）
from vnpy_ctastrategy import CtaStrategyApp               # CTA趋势跟踪策略引擎
from vnpy_ctabacktester import CtaBacktesterApp           # CTA策略历史回测模块
# from vnpy_spreadtrading import SpreadTradingApp         # 价差套利交易模块
# from vnpy_algotrading import AlgoTradingApp             # 算法交易执行模块（TWAP/VWAP/冰山等）
# from vnpy_optionmaster import OptionMasterApp           # 期权策略分析与定价模块
# from vnpy_portfoliostrategy import PortfolioStrategyApp # 组合级别策略模块（多品种协同）
# from vnpy_scripttrader import ScriptTraderApp           # 脚本策略交易模块（CLI命令行交易）
from vnpy_chartwizard import ChartWizardApp             # K线图表向导组件
# from vnpy_rpcservice import RpcServiceApp               # RPC跨进程服务（远程调用交易接口）
# from vnpy_excelrtd import ExcelRtdApp                   # Excel RTD实时数据服务
from vnpy_datamanager import DataManagerApp               # 数据管理模块（导入/导出/查看历史数据）
# from vnpy_datarecorder import DataRecorderApp           # 行情录制模块（Tick/K线数据自动入库）
# from vnpy_riskmanager import RiskManagerApp             # 风控管理模块（仓位/订单/资金风控）
# from vnpy_webtrader import WebTraderApp                 # Web端交易界面
# from vnpy_portfoliomanager import PortfolioManagerApp   # 投资组合管理模块


def main():
    """"""
    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    main_engine.add_gateway(CtpGateway)                 # 加载CTP交易接口
    # main_engine.add_gateway(CtptestGateway)           # 加载CTP穿透式测试接口
    # main_engine.add_gateway(MiniGateway)              # 加载迷你股指期货接口
    # main_engine.add_gateway(FemasGateway)             # 加载飞马期货接口
    # main_engine.add_gateway(SoptGateway)              # 加载上证股票期权接口
    # main_engine.add_gateway(EsunnyGateway)            # 加载易盛国际期货接口
    # main_engine.add_gateway(XtpGateway)               # 加载中泰XTP证券接口
    # main_engine.add_gateway(ToraStockGateway)         # 加载华鑫奇点股票接口
    # main_engine.add_gateway(ToraOptionGateway)        # 加载华鑫奇点期权接口
    # main_engine.add_gateway(IbGateway)                # 加载盈透证券接口
    # main_engine.add_gateway(TapGateway)               # 加载易盛Tap接口
    # main_engine.add_gateway(DaGateway)                # 加载直达国际期货接口
    # main_engine.add_gateway(RohonGateway)             # 加载融航资管接口
    # main_engine.add_gateway(TtsGateway)               # 加载TTS仿真交易接口

    main_engine.add_app(PaperAccountApp)             # 加载模拟交易账户
    main_engine.add_app(CtaStrategyApp)                  # 加载CTA策略引擎
    main_engine.add_app(CtaBacktesterApp)                # 加载CTA回测模块
    # main_engine.add_app(SpreadTradingApp)              # 加载价差套利模块
    # main_engine.add_app(AlgoTradingApp)                # 加载算法交易模块
    # main_engine.add_app(OptionMasterApp)               # 加载期权策略模块
    # main_engine.add_app(PortfolioStrategyApp)          # 加载组合策略模块
    # main_engine.add_app(ScriptTraderApp)               # 加载脚本交易模块
    main_engine.add_app(ChartWizardApp)                # 加载K线图表组件
    # main_engine.add_app(RpcServiceApp)                 # 加载RPC服务模块
    # main_engine.add_app(ExcelRtdApp)                   # 加载Excel RTD服务
    main_engine.add_app(DataManagerApp)                  # 加载数据管理模块
    # main_engine.add_app(DataRecorderApp)               # 加载行情录制模块
    # main_engine.add_app(RiskManagerApp)                # 加载风控管理模块
    # main_engine.add_app(WebTraderApp)                  # 加载Web交易界面
    # main_engine.add_app(PortfolioManagerApp)           # 加载组合管理模块

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    main()
