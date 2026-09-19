#include <assert.h>
#include <stdio.h>
#include "../qcom_pld_protocol.h"

struct fake {
	u32 head_value;
	u32 min_offset, max_offset;
	unsigned int head_reads, power_reads;
	int tear_head, tear_data, field_mode;
	u16 value;
};

static u32 read_head(void *context)
{
	struct fake *f = context;

	f->head_reads++;
	if (f->tear_head == 2)
		return f->head_value + (f->head_reads <= 3 ? f->head_reads : 3);
	return f->head_value + (f->tear_head ? f->head_reads : 0);
}

static u16 read_power(void *context, u32 offset)
{
	struct fake *f = context;

	assert(!(offset & 1));
	assert(offset >= PLD_RECORDS && offset + 2 <= PLD_SIZE);
	if (offset < f->min_offset)
		f->min_offset = offset;
	if (offset > f->max_offset)
		f->max_offset = offset;
	f->power_reads++;
	if (f->field_mode)
		return (offset - PLD_RECORDS) % PLD_RECORD_SIZE;
	return f->tear_data ? f->power_reads : f->value;
}

int main(void)
{
	struct fake f = { .head_value = 1, .min_offset = ~0U, .value = 1234 };
	struct pld_io io = { &f, read_head, read_power };
	struct pld_sample s;

	assert(pld_snapshot(&io, &s) == 0);
	assert(s.head == 1 && s.power[0] == 1234);
	assert(f.min_offset == PLD_RECORDS + 8);
	assert(f.max_offset == PLD_RECORDS + 28);
	assert(pld_microwatts(s.power[0]) == 12340000);
	assert(pld_microwatts(65534) == 655340000);
	f.field_mode = 1;
	assert(pld_snapshot(&io, &s) == 0);
	assert(s.power[0] == 8 && s.power[1] == 10 && s.power[2] == 12);
	assert(s.power[3] == 14 && s.power[4] == 26 && s.power[5] == 28);
	assert(s.power[6] == 24);
	f.field_mode = 0;
	/* A zero reading is valid; freshness is a separate condition. */
	f.value = 0;
	assert(pld_snapshot(&io, &s) == 0 && s.power[6] == 0);
	f.value = 0xffff;
	assert(pld_snapshot(&io, &s) == -ENODATA);
	f.value = 42;
	f.tear_head = 1;
	f.head_reads = f.power_reads = 0;
	assert(pld_snapshot(&io, &s) == -EIO);
	assert(f.head_reads == 12 && f.power_reads == 56);
	f.tear_head = 2;
	f.head_reads = f.power_reads = 0;
	assert(pld_snapshot(&io, &s) == 0);
	assert(f.head_reads == 6 && f.power_reads == 28);
	f.tear_head = 0;
	f.tear_data = 1;
	f.head_reads = f.power_reads = 0;
	assert(pld_snapshot(&io, &s) == -EIO);
	assert(f.head_reads == 12 && f.power_reads == 56);
	f.tear_data = 0;
	for (unsigned int i = 0; i < 65536; i++) {
		f.head_value = i * 65537U;
		f.min_offset = ~0U;
		f.max_offset = 0;
		assert(pld_snapshot(&io, &s) == 0);
		assert(f.max_offset < PLD_RECORDS + PLD_CAPACITY * PLD_RECORD_SIZE);
	}
	puts("protocol: offsets/units/zero/sentinel/torn-head/torn-data/bounded-retry/wrap passed");
	return 0;
}
