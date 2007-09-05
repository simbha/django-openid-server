
"""
This module implements an example server for the OpenID library.  Some
functionality has been omitted intentionally; this code is intended to
be instructive on the use of this library.  This server does not
perform actual user authentication and serves up only one OpenID URL,
with the exception of IDP-generated identifiers.

Some code conventions used here:

* 'request' is a Django request object.

* 'openid_request' is an OpenID library request object.

* 'openid_response' is an OpenID library response
"""

import cgi

from djopenid import util
from djopenid.util import getViewURL

from django import http
from django.views.generic.simple import direct_to_template

from openid.server.server import Server, ProtocolError, CheckIDRequest, \
     EncodingError
from openid.server.trustroot import verifyReturnTo
from openid.yadis.discover import DiscoveryFailure
from openid import sreg

def getOpenIDStore():
    """
    Return an OpenID store object fit for the currently-chosen
    database backend, if any.
    """
    return util.getOpenIDStore('/tmp/djopenid_s_store', 's_')

def getServer(request):
    """
    Get a Server object to perform OpenID authentication.
    """
    return Server(getOpenIDStore(), getViewURL(request, endpoint))

def setRequest(request, openid_request):
    """
    Store the openid request information in the session.
    """
    if openid_request:
        request.session['openid_request'] = openid_request
    else:
        request.session['openid_request'] = None

def getRequest(request):
    """
    Get an openid request from the session, if any.
    """
    return request.session.get('openid_request')

def server(request):
    """
    Respond to requests for the server's primary web page.
    """
    return direct_to_template(
        request,
        'server/index.html',
        {'user_url': getViewURL(request, idPage),
         'server_xrds_url': getViewURL(request, idpXrds),
         })

def idpXrds(request):
    """
    Respond to requests for the IDP's XRDS document, which is used in
    IDP-driven identifier selection.
    """
    r = direct_to_template(request, 'server/xrds.html',
                           {'server_url': getViewURL(request, endpoint)})
    r['Content-Type'] = 'application/xrds+xml'
    return r

def idPage(request):
    """
    Serve the identity page for OpenID URLs.
    """
    return direct_to_template(
        request,
        'server/idPage.html',
        {'server_url': getViewURL(request, endpoint)})

def trustPage(request):
    """
    Display the trust page template, which allows the user to decide
    whether to approve the OpenID verification.
    """
    return direct_to_template(
        request,
        'server/trust.html',
        {'trust_handler_url':getViewURL(request, processTrustResult)})

def endpoint(request):
    """
    Respond to low-level OpenID protocol messages.
    """
    s = getServer(request)

    query = util.normalDict(request.GET or request.POST)

    # First, decode the incoming request into something the OpenID
    # library can use.
    try:
        openid_request = s.decodeRequest(query)
    except ProtocolError, why:
        # This means the incoming request was invalid.
        return direct_to_template(
            request,
            'server/endpoint.html',
            {'error': str(why)})

    # If we did not get a request, display text indicating that this
    # is an endpoint.
    if openid_request is None:
        return direct_to_template(
            request,
            'server/endpoint.html',
            {})

    # We got a request; if the mode is checkid_*, we will handle it by
    # getting feedback from the user or by checking the session.
    if openid_request.mode in ["checkid_immediate", "checkid_setup"]:
        return handleCheckIDRequest(request, openid_request)
    else:
        # We got some other kind of OpenID request, so we let the
        # server handle this.
        openid_response = s.handleRequest(openid_request)
        return displayResponse(request, openid_response)

def handleCheckIDRequest(request, openid_request):
    """
    Handle checkid_* requests.  Get input from the user to find out
    whether she trusts the RP involved.  Possibly, get intput about
    what Simple Registration information, if any, to send in the
    response.
    """
    if openid_request.immediate:
        # Always respond with 'cancel' to immediate mode requests
        # because we don't track information about a logged-in user.
        # If we did, then the answer would depend on whether that user
        # had trusted the request's trust root and whether the user is
        # even logged in.
        openid_response = openid_request.answer(False)
        return displayResponse(request, openid_response)
    else:
        # Store the incoming request object in the session so we can
        # get to it later.
        setRequest(request, openid_request)
        return showDecidePage(request, openid_request)

def showDecidePage(request, openid_request):
    """
    Render a page to the user so a trust decision can be made.

    @type openid_request: openid.server.server.CheckIDRequest
    """
    idSelect = openid_request.idSelect()
    identity = openid_request.identity
    trust_root = openid_request.trust_root
    default_url = getViewURL(request, idPage)
    return_to = openid_request.return_to

    try:
        # Stringify because template's ifequal can only compare to strings.
        trust_root_valid = verifyReturnTo(trust_root, return_to) \
                           and "Valid" or "Invalid"
    except DiscoveryFailure, err:
        trust_root_valid = "DISCOVERY_FAILED"

    return direct_to_template(
        request,
        'server/trust.html',
        {'idSelect': idSelect,
         'identity': identity,
         'trust_root': trust_root,
         'default_url': default_url,
         'trust_handler_url':getViewURL(request, processTrustResult),
         'trust_root_valid': trust_root_valid,
         })

def processTrustResult(request):
    """
    Handle the result of a trust decision and respond to the RP
    accordingly.
    """
    # Get the request from the session so we can construct the
    # appropriate response.
    openid_request = getRequest(request)

    result = None
    response_identity = openid_request.identity

    # If the decision was to allow the verification, respond
    # accordingly.
    if 'allow' in request.POST:
        result = True
    elif 'cancel' in request.POST:
        # Otherwise, respond with False.
        result = False

    # If the request was an IDP-driven identifier selection request
    # (i.e., the IDP URL was entered at the RP), look at the form to
    # find out what identity URL the user wanted to send.
    if openid_request.idSelect():
        response_identity = getViewURL(
            request,
            idPage, kwargs={'name':request.POST['name']})

    # Generate a response with the appropriate answer.
    openid_response = openid_request.answer(result,
                                            identity=response_identity)

    # Send Simple Registration data in the response, if appropriate.
    if result:
        sreg_data = {
            'fullname': 'Example User',
            'nickname': 'example',
            'dob': '1970-01-01',
            'email': 'invalid@example.com',
            'gender': 'F',
            'postcode': '12345',
            'country': 'ES',
            'language': 'eu',
            'timezone': 'America/New_York',
            }

        sreg_req = sreg.SRegRequest.fromOpenIDRequest(openid_request)
        sreg_resp = sreg.SRegResponse.extractResponse(sreg_req, sreg_data)
        openid_response.addExtension(sreg_resp)

    return displayResponse(request, openid_response)

def displayResponse(request, openid_response):
    """
    Display an OpenID response.  Errors will be displayed directly to
    the user; successful responses and other protocol-level messages
    will be sent using the proper mechanism (i.e., direct response,
    redirection, etc.).
    """
    s = getServer(request)

    # Encode the response into something that is renderable.
    try:
        webresponse = s.encodeResponse(openid_response)
    except EncodingError, why:
        # If it couldn't be encoded, display an error.
        text = why.response.encodeToKVForm()
        return direct_to_template(
            request,
            'server/endpoint.html',
            {'error': cgi.escape(text)})

    # Construct the appropriate django framework response.
    r = http.HttpResponse(webresponse.body)
    r.status_code = webresponse.code

    for header, value in webresponse.headers.iteritems():
        r[header] = value

    return r
