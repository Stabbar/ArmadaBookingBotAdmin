import json
import os

from config import TEMPLATES_FILE, DEFAULT_TEMPLATES


def load_templates():
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_TEMPLATES


def save_templates(templates):
    with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

class TemplatesManager:
    def __init__(self):
        self.templates = load_templates()

    def add_template(self, name, template_text):
        if name.lower() in self.templates:
            return False
        self.templates[name.lower()] = template_text
        save_templates(self.templates)
        return True

    def edit_template(self, name, new_text):
        if name.lower() not in self.templates:
            return False
        self.templates[name.lower()] = new_text
        save_templates(self.templates)
        return True

    def get_template(self, name='default'):
        return self.templates.get(name.lower(), self.templates['default'])

    def list_templates(self):
        return list(self.templates.keys())

    def delete_template(self, name):
        if name.lower() == 'default' or name.lower() not in self.templates:
            return False
        del self.templates[name.lower()]
        save_templates(self.templates)
        return True