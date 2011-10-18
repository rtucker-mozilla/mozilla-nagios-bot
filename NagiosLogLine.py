import re
class NagiosLogLine:
    def __init__(self, line):
        self.is_service = False
        self.line = line.strip()
        self.notification_list = []
        self.notification_recipient = None
        self.notification_type = None
        self.host = None
        self.service = None
        self.message = None
        self._is_notification()
        
        if self.is_notification:
            self.notification_type = self._get_notification_type()
            self._build_notification_list()
            self.notification_recipient = self._get_notification_recipient()
            self.host = self._get_host()
            self.service = self._get_service()
            self.state = self._get_state()
            self.message = self._get_message()

    def _get_host(self):
        return self.notification_list[1]

    def _get_service(self):
        if self.is_service:
            self.is_service = True
            return self.notification_list[2]
        else:
            return None

    def _get_state(self):
        if self.is_service:
            return self.notification_list[3]
        else:
            return self.notification_list[2]

    def _get_message(self):
        if self.is_service:
            return self.notification_list[5]
        else:
            return self.notification_list[4]

    def _is_notification(self):
        m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION:", self.line)
        if m:
            self.is_notification = True
        else:
            self.is_notification = False

    def _build_notification_list(self):
        m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION: ((?:sysalertsonly|guest|servicesalertslist|sysalertslist|buildteam|dougt|camino|seamonkey|tdsmirrors|sumo-dev|socorroalertlist|metrics|laura);(.*))$", self.line)
        self.notification_list = m.group(2).split(";")

    def _get_notification_recipient(self):
        return self.notification_list[0]

    def _get_notification_type(self):
        m = re.search("^\[\d+\]\s(HOST|SERVICE) NOTIFICATION:", self.line)
        if m:
            if m.group(1) == 'HOST':
                return 'HOST'
            elif m.group(1) == 'SERVICE':
                self.is_service = True
                return 'SERVICE'
            else:
                return False
