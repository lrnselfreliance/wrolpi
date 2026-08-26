# AI module test fixtures.  The docs conftest is not star-imported by the root conftest, but the
# AI endpoints cover docs; import its fixtures so AI tests can use doc_factory.
from modules.docs.conftest import *  # noqa
