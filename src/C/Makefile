all: kpw kpw2 kcw kpw2_192 bab kpw2_512 fullcount

kpw: kpw.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ $<

kcw: kcw.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ $<

kpw2: kpw2.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ $<

kpw2_192: kpw2.c
	$(CC) -O3 -march=native -Wall -Wextra -DW=3 -o $@ $<

kpw2_512: kpw2.c
	$(CC) -O3 -march=native -Wall -Wextra -DW=8 -o $@ $<

bab: bab.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ $<

fullcount: fullcount.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ $<
