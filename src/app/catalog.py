from .models import Expert, Skill

SKILLS = [
    Skill(id="python", name="Python 工程", description="编写、调试和重构 Python 程序", tags=["python", "代码", "后端"], capabilities=["coding", "debugging"]),
    Skill(id="data-analysis", name="数据分析", description="清洗数据、统计分析、生成图表和报告", tags=["数据", "分析", "报表", "可视化"], capabilities=["data", "visualization"]),
    Skill(id="web-research", name="网络调研", description="搜索、核验并总结公开网页信息", tags=["搜索", "调研", "网页"], capabilities=["research"], risk_level="medium"),
    Skill(id="docx", name="Word 文档", description="创建和编辑专业 Word 文档", tags=["word", "docx", "文档"], capabilities=["document"]),
    Skill(id="browser", name="浏览器自动化", description="操作浏览器、填写页面和提取信息", tags=["浏览器", "网页", "自动化"], capabilities=["browser"], risk_level="high"),
]

EXPERTS = [
    Expert(id="python-fullstack", name="Python 全栈工程师", description="负责 Web、数据、AI 和自动化工程", tags=["python", "代码", "web", "ai", "自动化"], capabilities=["coding", "data", "debugging"], skill_ids=["python", "data-analysis"]),
    Expert(id="researcher", name="研究分析师", description="负责公开资料检索、比较和证据整理", tags=["调研", "搜索", "研究", "网页"], capabilities=["research", "data"], skill_ids=["web-research", "data-analysis"]),
    Expert(id="document-specialist", name="文档专家", description="负责结构化写作和专业文档交付", tags=["文档", "写作", "word", "报告"], capabilities=["document"], skill_ids=["docx", "data-analysis"]),
]
