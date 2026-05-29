from pathlib import Path

general_prompt = """
 # 角色                                                                                                                       
 你是人工智能助手。                                                                                      
                                                                                                                              
 # 行为准则                                                                                                                   
 1. 简洁精准，不啰嗦                                                                                                          
 2. 不确定时明确说明，不编造   
 """


def load_prompt(name: str, **kwargs) -> str:
    try:
        template = (Path(__file__).parent / f"{name}").read_text(encoding="utf-8")
        # 简单替换，或引入 Jinja2
        for k, v in kwargs.items():
            template = template.replace(f"{{{{{k}}}}}", str(v))
    except FileNotFoundError:
        template = general_prompt
    return template


Assistant_PROMPT = load_prompt("system_prompt.md")
