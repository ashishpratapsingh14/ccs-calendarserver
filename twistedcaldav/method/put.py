##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV PUT method.
"""

__all__ = ["http_PUT"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import twisted_dav_namespace
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import allDataFromStream, parentForURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav import customxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.dropbox import DropBox
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.notifications import Notification
from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_PUT(self, request):

    parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
    yield parent
    parent = parent.getResult()

    if isPseudoCalendarCollectionResource(parent):
        self.fp.restat(False)

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (content_type,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
            
        # Read the calendar component from the stream
        try:
            d = waitForDeferred(allDataFromStream(request.stream))
            yield d
            calendardata = d.getResult()

            # We must have some data at this point
            if calendardata is None:
                # Use correct DAV:error response
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

            d = waitForDeferred(storeCalendarObjectResource(
                request = request,
                sourcecal = False,
                calendardata = calendardata,
                destination = self,
                destination_uri = request.uri,
                destinationcal = True,
                destinationparent = parent,)
            )
            yield d
            yield d.getResult()
            return

        except ValueError, e:
            log.err("Error while handling (calendar) PUT: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    elif DropBox.enabled and parent.isSpecialCollection(customxml.DropBoxHome):
        # Cannot create resources in a drop box home collection
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (twisted_dav_namespace, "valid-drop-box")))

    elif DropBox.enabled and parent.isSpecialCollection(customxml.DropBox):
        # We need to handle notificiations
        
        # We need the current etag
        if self.exists() and self.etag() is not None:
            oldETag = self.etag().generate()
        else:
            oldETag = None
        
        # Do the normal http_PUT behavior
        d = waitForDeferred(super(CalDAVFile, self).http_PUT(request))
        yield d
        response = d.getResult()
        
        if response.code in (responsecode.OK, responsecode.CREATED, responsecode.NO_CONTENT):

            authid = None
            if isinstance(request.authnUser.children[0], davxml.HRef):
                authid = str(request.authnUser.children[0])

            if self.exists() and self.etag() is not None:
                newETag = self.etag().generate()
            else:
                newETag = None
            
            if response.code == responsecode.CREATED:
                oldURI = None
                newURI = request.uri
            else:
                oldURI = request.uri
                newURI = None

            notification = Notification(action={
                responsecode.OK         : Notification.ACTION_MODIFIED,
                responsecode.CREATED    : Notification.ACTION_CREATED,
                responsecode.NO_CONTENT : Notification.ACTION_MODIFIED,
            }[response.code], authid=authid, oldURI=oldURI, newURI=newURI, oldETag=oldETag, newETag=newETag)
            d = waitForDeferred(notification.doNotification(request, parent, self))
            yield d
            d.getResult()
        
        yield response
        return

    else:
        d = waitForDeferred(super(CalDAVFile, self).http_PUT(request))
        yield d
        yield d.getResult()

http_PUT = deferredGenerator(http_PUT)
