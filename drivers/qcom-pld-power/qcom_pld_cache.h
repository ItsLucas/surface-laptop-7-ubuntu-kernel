/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef QCOM_PLD_CACHE_H
#define QCOM_PLD_CACHE_H

#include <linux/errno.h>
#include <linux/types.h>

#define QCOM_PLD_STALE_NS 3000000000ULL

struct qcom_pld_freshness {
	u32 head;
	u64 observed_ns;
	u64 fresh_after_ns;
	bool seeded;
	bool live;
};

static inline int qcom_pld_cached_status(const struct qcom_pld_freshness *s,
					u64 now, int error, bool suspended)
{
	if (suspended)
		return -ENODATA;
	if (error)
		return error;
	if (!s->live || now < s->fresh_after_ns ||
	    now - s->fresh_after_ns > QCOM_PLD_STALE_NS)
		return -ENODATA;
	return 0;
}

/*
 * Freshness is bounded by the PREVIOUS observation, not the time we notice
 * a new head: after a long polling gap, even a changed head may be stale.
 * -EAGAIN requests another observation; the caller bounds that wait.
 */
static inline int qcom_pld_observe(struct qcom_pld_freshness *s,
				 u32 head, u64 now)
{
	u32 delta = head - s->head;

	if (!s->seeded || now < s->observed_ns ||
	    now - s->observed_ns > QCOM_PLD_STALE_NS ||
	    delta > 0x7fffffffU ||
	    delta > (now - s->observed_ns) / 1000000000ULL + 2) {
		s->seeded = true;
		s->live = false;
	} else if (delta) {
		s->live = true;
		s->fresh_after_ns = s->observed_ns;
	}
	s->head = head;
	s->observed_ns = now;
	if (s->live && now - s->fresh_after_ns <= QCOM_PLD_STALE_NS)
		return 0;
	s->live = false;
	return -EAGAIN;
}

#endif
