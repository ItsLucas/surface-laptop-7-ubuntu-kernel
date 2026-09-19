#include <assert.h>
#include <stdio.h>
#include "../qcom_pld_cache.h"

#define MS(x) ((u64)(x) * 1000000ULL)

int main(void)
{
	struct qcom_pld_freshness s = { 0 };

	assert(qcom_pld_cached_status(&s, MS(1), 0, false) == -ENODATA);
	assert(qcom_pld_cached_status(&s, MS(1), -EIO, false) == -EIO);
	assert(qcom_pld_cached_status(&s, MS(1), -EIO, true) == -ENODATA);

	/* Initial retained data, including a zero head, is not live. */
	assert(qcom_pld_observe(&s, 0, MS(100)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 0, MS(200)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 1, MS(1100)) == 0);
	assert(qcom_pld_cached_status(&s, MS(1100), 0, false) == 0);
	assert(qcom_pld_cached_status(&s, MS(3201), 0, false) == -ENODATA);
	assert(qcom_pld_observe(&s, 1, MS(2100)) == 0);
	assert(qcom_pld_observe(&s, 1, MS(3201)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 2, MS(3300)) == 0);

	/* A changed counter after a long gap does not prove recent data. */
	assert(qcom_pld_observe(&s, 20, MS(20000)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 20, MS(20100)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 21, MS(21000)) == 0);

	/* Firmware reset is a new session, not a huge forward increment. */
	assert(qcom_pld_observe(&s, 2, MS(22000)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 3, MS(23000)) == 0);
	/* A forward reset or corruption also cannot claim a fresh epoch. */
	assert(qcom_pld_observe(&s, 5000, MS(23010)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 5001, MS(24010)) == 0);

	/* Genuine u32 wrap, including ffffffff and zero, remains valid. */
	s = (struct qcom_pld_freshness){ 0 };
	assert(qcom_pld_observe(&s, 0xfffffffeU, MS(100)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 0xffffffffU, MS(1100)) == 0);
	assert(qcom_pld_observe(&s, 0, MS(2100)) == 0);

	/* PM resume clears the whole epoch, even if the head is unchanged. */
	s = (struct qcom_pld_freshness){ 0 };
	assert(qcom_pld_observe(&s, 100, MS(50000)) == -EAGAIN);
	assert(qcom_pld_observe(&s, 101, MS(51000)) == 0);
	assert(qcom_pld_observe(&s, 102, MS(10)) == -EAGAIN);
	puts("freshness: initial/stale/gap/reset/u32-wrap/resume/time-regression passed");
	return 0;
}
