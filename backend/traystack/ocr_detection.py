"""Expose raw contour truncation from RapidOCR 3.10.0 before box filtering."""

import cv2
import numpy as np
from rapidocr.ch_ppocr_det.utils import DBPostProcess


class LimitAwarePostProcess(DBPostProcess):
    limit_hit = False
    raw_contours = 0

    def boxes_from_bitmap(self, pred, bitmap, dest_width, dest_height):
        # This is the same mask/contour mode used by the pinned upstream method.
        # Count before its size/score filtering, which can hide discarded content.
        contours = cv2.findContours(
            (bitmap * 255).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )[-2]
        self.raw_contours = max(self.raw_contours, len(contours))
        self.limit_hit = self.limit_hit or len(contours) > self.max_candidates
        return super().boxes_from_bitmap(pred, bitmap, dest_width, dest_height)


def observe_detection(engine):
    # Version-pinned RapidOCR exposes no public pre-filter contour-limit flag.
    detector = engine._load_det_model()
    original = detector.postprocess_op
    detector.postprocess_op = LimitAwarePostProcess(
        thresh=original.thresh,
        box_thresh=original.box_thresh,
        max_candidates=original.max_candidates,
        unclip_ratio=original.unclip_ratio,
        score_mode=original.score_mode,
        use_dilation=original.dilation_kernel is not None,
    )
    return detector.postprocess_op
