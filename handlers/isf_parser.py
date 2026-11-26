import json5

class ISFHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self.content = ""
        self.inputs = []
        self.description = ""
        self.credit = ""
        self.isfvsn = ""
        self._parse_file()

    def _parse_file(self):
        with open(self.file_path, 'r') as f:
            self.content = f.read()
        import json
        import re
        match = re.search(r'/\*\{(.*)\}\*/', self.content, re.DOTALL)
        if match:
            metadata = json.loads("{" + match.group(1) + "}")
            self.inputs = metadata.get("INPUTS", [])
            self.description = metadata.get("DESCRIPTION", "")
            self.credit = metadata.get("CREDIT", "")
            self.isfvsn = metadata.get("ISFVSN", "")