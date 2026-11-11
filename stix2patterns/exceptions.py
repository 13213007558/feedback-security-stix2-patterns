from antlr4.error.ErrorListener import ErrorListener


class STIXPatternErrorListener(ErrorListener):
    """
    Modifies ErrorListener to collect error message and set flag to False when
    invalid pattern is encountered.
    """
    def __init__(self):
        super(STIXPatternErrorListener, self).__init__()
        self.err_strings = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self.err_strings.append("FAIL: Error found at line %d:%d. %s" %
                                (line, column, msg))


class ParserErrorListener(ErrorListener):
    """
    Simple error listener which just remembers the last error message received.
    """
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self.error_message = u"{}:{}: {}".format(line, column, msg)


class ParseException(Exception):
    """Represents a parse error."""
    pass


class UnknownSTIXVersionError(ValueError):
    """
    Raised when a caller requests a STIX specification version this library
    does not understand.  The library never silently falls back to a default
    version in this situation: an explicit, unsupported version is always an
    error.
    """
    def __init__(self, version, supported_versions):
        self.version = version
        self.supported_versions = tuple(supported_versions)

        message = (
            "Unknown STIX version %r. Supported versions are: %s."
            % (version, ", ".join(self.supported_versions))
        )

        super(UnknownSTIXVersionError, self).__init__(message)
