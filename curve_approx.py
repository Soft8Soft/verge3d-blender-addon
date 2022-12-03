import numpy as np


DEFAULT_MAX_SEGM_ERROR = 1e-3
MIN_MAX_SEGM_ERROR = 1e-5


def calcCurveApproximationErrors(dataX, dataY, approxIndices, optSingleSegment=False):
    """
    Calculate errors of the approximation defined by the given indices for the
    original data. The errors are calculated for each segment as areas between
    2 piecewise linear functions: formed by the original points and by the
    approximated ones.

    Args:
        dataX (numpy.ndarray[float]): X coordinates defining the original curve.
        dataY (numpy.ndarray[float]): Y coordinates defining the original curve.
        approxIndices (numpy.ndarray[int]): Indices that specify a subset of the
            input data corresponding to the approximation. The first and the
            last indices must always be present.
        optSingleSegment (bool): Does the approxIndices data represent a single
            approximating segment (by being equal to [0, len(dataX) - 1]) or not.
            For a single segment setting this to True can improve performance.
            Defaults to False.

    Return:
        List: Errors for each individual approximated segment.
    """

    # The sampled data is usually more sparse than the original data and has
    # larger segments. Need to interpolate those segments at original x points
    # to make the sampled dataset the same length as the original one. That
    # makes it easier to integrate the difference between the datasets.
    if optSingleSegment:
        x0 = dataX[0]
        x1 = dataX[-1]
        y0 = dataY[0]
        y1 = dataY[-1]
        approxY = (y1 - y0) / (x1 - x0) * (dataX - x0) + y0
    else:
        approxY = np.interp(dataX, dataX[approxIndices], dataY[approxIndices])

    # The dataset for the "difference" piecewise function.
    diffX = dataX
    diffY = dataY - approxY

    diffYLeft = diffY[:-1]
    diffYRight = diffY[1:]

    # OPT: slicing faster than np.diff here
    trapzLateral = diffX[1:] - diffX[:-1] # h - bottom lateral side orthogonal to both bases
    trapzLeftBase = np.abs(diffYLeft)     # a - left base side
    trapzRightBase = np.abs(diffYRight)   # b - right base side

    # Both positive and negative areas calculated during integration should add
    # to the overall error. That's why we use here the module of the
    # "difference" function for integration. This is done via computing the
    # areas of the corresponding trapezoids with an only exception when the
    # "difference" function intersects the abscissa axis - need to exclude the
    # areas of the 2 inner lateral triangles in such cases.
    trapzArea = trapzLateral * (trapzLeftBase + trapzRightBase) / 2

    with np.errstate(invalid='ignore'):
        # 0 value in the denominator means that both trapezoid bases have 0
        # length. In such cases the area of the lateral triangles isn't used
        # anyway.
        trapzLateralArea = (trapzLeftBase * trapzRightBase * trapzLateral / (trapzLeftBase + trapzRightBase))

    intersectsAbscissa = diffYLeft * diffYRight < 0
    errors = np.subtract(trapzArea, trapzLateralArea, out=trapzArea,
            where=intersectsAbscissa)

    segmentErrors = []
    for i in range(len(approxIndices) - 1):
        idxFrom = approxIndices[i]
        idxTo = approxIndices[i + 1]
        segmentErrors.append(np.sum(errors[idxFrom:idxTo]))

    return segmentErrors

def approximateCurveMulti(x, yArrays, mandatoryIndicesMask=None,
        maxSegmentErrors=None):
    """
    Calculate single piecewise approximation that fit multiple curves. All
    curves are defined by the same x and individual y coordinates from the
    yArrays argument.

    Args:
        x (numpy.ndarray[float]): X coordinates defining the original curves.
        yArrays (List[numpy.ndarray[float]]): list of numpy.ndarray of Y
            coordinates defining the original curves.
        mandatoryIndicesMask (numpy.ndarray[bool], optional): An array denoting
            which points from the input data that should always be presented in
            the approximation, i.e [True, True, False, ...].  Defaults to None.
            The first and the last points of the input data are always
            mandatory.
        maxSegmentErrors(List, optional): Maximum allowed segment errors for
            each original curves. The lower the value the more points will be
            in the approximation. Defaults to None, which means that
            DEFAULT_MAX_SEGM_ERROR will be used for all curves instead.

    Returns:
        List[int]: Indices that specify a subset of the input data
            corresponding to the approximation.

    Raises:
        ValueError: If the input data length is not sufficient (length of x < 2).
    """

    if len(x) < 2:
        raise ValueError('Length of the input x data is less than 2.')

    if mandatoryIndicesMask is None:
        mandatoryIndicesMask = np.full(len(x), False)
    mandatoryIndicesMask[0] = True
    mandatoryIndicesMask[len(x) - 1] = True

    if maxSegmentErrors is None:
        maxSegmentErrors = [DEFAULT_MAX_SEGM_ERROR] * len(yArrays)

    # This prevents issues with curves that get 0 maximum segment error (e.g.
    # that can happen with curves parallel to abscissa). Any calculation error
    # exceeds the limit of 0, and therefore would lead to adding redundant
    # points to the resulting approximation without such workaround.
    maxSegmentErrors = [max(err, MIN_MAX_SEGM_ERROR) for err in maxSegmentErrors]

    # OPT: this halves the calculated cross product, so it gives the desired
    # triangle area as a result. It's faster to apply this to the whole X data
    # here than to divide by 2 on each loop iteration.
    xHalved = x / 2

    # OPT: after expanding and rearranging the cross product formula used
    # further it appears that some summands can be batch calculated. This saves
    # several additions on each loop iteration.
    c0 = [xHalved[:-1] * y[1:] - xHalved[1:] * y[:-1] for y in yArrays]
    c1 = [np.diff(y) for y in yArrays]
    c2 = np.diff(xHalved)

    prevSampledIdx = -1
    sampledIndices = []
    accumulatedTriArea = np.zeros(len(yArrays))

    for i in range(len(xHalved)):
        if mandatoryIndicesMask[i]:
            prevSampledIdx = i
            sampledIndices.append(i)
            accumulatedTriArea.fill(0)
            continue

        # Testing the next point if the corresponding segment exceeds
        # the limit criteria.
        for yIdx, y in enumerate(yArrays):
            # OPT: inline cross faster than calling a separate function
            crossHalved = c0[yIdx][i] - xHalved[prevSampledIdx] * c1[yIdx][i] + y[prevSampledIdx] * c2[i]

            # The area can be calculated by adding cross results of all
            # consecutive triangles that form the overall error area (even for
            # concave areas). This is not correct in case if the approximating
            # segment intersects the original polyline in the middle, but the
            # result becomes the lower bound and that is still useful.
            accumulatedTriArea[yIdx] += crossHalved

            if abs(accumulatedTriArea[yIdx]) > maxSegmentErrors[yIdx]:
                prevSampledIdx = i
                sampledIndices.append(i)
                accumulatedTriArea.fill(0)
                break

    return sampledIndices
