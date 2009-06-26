#!/usr/bin/python

from math import sqrt

def dist_line_point(A, B, p):
    #CGAlgorithms::distancePointLine comp.graphics.algorthim FAQ via GEOS

    s=(((A[1]-p[1])*(B[0]-A[0])-(A[0]-p[0])*(B[1]-A[1])) /
       ((B[0]-A[0])*(B[0]-A[0])+(B[1]-A[1])*(B[1]-A[1])))
    return abs(s)*sqrt(((B[0]-A[0])*(B[0]-A[0])+(B[1]-A[1])*(B[1]-A[1])))


#This approximates the postgresql function of the same name.  For some
#reason, it gives slightly different results.  Since I haven't looked
#at the postgresql function, I don't know why.  It's also slower than
#going through postgresql, but using postgresql appears to cause
#segfaults after some internal resource is exhausted.
def st_line_locate_point(linestring, p):

    coords = linestring.coords
    before_length = after_length = seg_length = 0
    best_dist = 1000000000

    found = None
    for i in range(len(coords) - 1):
        p0, p1 = coords[i:i+2]
        this_length = sqrt((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) **2)
        # next four lines from comp.graphics.algorithms Frequently
        # Asked Questions  via GEOS

        dx=p1[0]-p0[0]
        dy=p1[1]-p0[1]
        len2=dx*dx+dy*dy
        r=((p[0]-p0[0])*dx+(p[1]-p0[1])*dy)/len2

        if r < 0:
            r = 0
            dist = (p0[0] - p[0]) ** 2 + (p0[1] - p[1]) ** 2
        elif r > 1:
            r = 1
            dist = (p1[0] - p[0]) ** 2 + (p1[1] - p[1]) ** 2

        else:
            dist = dist_line_point(p0, p1, p)
            
        if dist < best_dist:
            best_dist = dist

            found = r
            before_length += after_length + seg_length
            after_length = 0
            seg_length = this_length
        else:
            if found is None:
                before_length += this_length
            else:
                after_length += this_length

    total_length = before_length + seg_length + after_length
    before_r = before_length / total_length
    seg_r = seg_length / total_length

    return before_r + found * seg_r
