from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

def main():
    qapp = create_qapp()
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    
    # 基础组件
    try:
        from vnpy_ctp import CtpGateway
        main_engine.add_gateway(CtpGateway)
    except Exception as e:
        print(f"网关加载失败: {e}")
        
    # 应用：CTA策略
    try:
        from vnpy_ctastrategy import CtaStrategyApp
        main_engine.add_app(CtaStrategyApp)
    except Exception as e:
        print(f"CTA策略应用加载失败: {e}")
        
    # 应用：数据管理
    try:
        from vnpy_datamanager import DataManagerApp
        main_engine.add_app(DataManagerApp)
    except Exception as e:
        print(f"数据管理应用加载失败: {e}")
    
    # 应用：本地仿真交易
    try:
        from vnpy_paperaccount import PaperAccountApp
        main_engine.add_app(PaperAccountApp)
    except Exception as e:
        print(f"仿真交易应用加载失败: {e}")
        
    # 应用：组合策略管理
    try:
        from vnpy_portfoliomanager import PortfolioManagerApp
        main_engine.add_app(PortfolioManagerApp)
    except Exception as e:
        print(f"组合策略管理加载失败: {e}")
        
    # 应用：价差交易
    try:
        from vnpy_spreadtrading import SpreadTradingApp
        main_engine.add_app(SpreadTradingApp)
    except Exception as e:
        print(f"价差交易应用加载失败: {e}")
        
    # 应用：图表工具
    try:
        from vnpy_chartwizard import ChartWizardApp
        main_engine.add_app(ChartWizardApp)
    except Exception as e:
        print(f"图表工具加载失败: {e}")
    
    # 启动界面
    try:
        main_window = MainWindow(main_engine, event_engine)
        main_window.show()
        qapp.exec()
    except Exception as e:
        print(f"界面启动失败: {e}")

if __name__ == "__main__":
    main()
