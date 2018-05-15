class JsonRPCError(Exception):

    def __init__(self, code, message):
        self.code = int(code)
        self.message = message

    def __str__(self):
        return "JsonRPC Error code: %d, Message: %s" % (self.code, self.message)