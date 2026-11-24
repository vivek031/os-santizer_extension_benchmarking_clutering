#!/usr/bin/perl
# perlbench-like text processing: tokenise, regex rewrite, count, sort.
use strict; use warnings;
my (%freq, $lines, $chars);
open(my $fh, '<', $ARGV[0]) or die "open: $!";
while (my $line = <$fh>) {
    $lines++;
    $line =~ s/\s+/ /g;
    $line =~ s/([A-Za-z_]\w*)\(/$1 (/g;
    $chars += length($line);
    my $up = uc($line);
    for my $w (split /[^A-Za-z0-9_]+/, $line) {
        next if length($w) < 3;
        $freq{lc $w}++;
    }
    my $joined = join('|', reverse split(/ /, $up));
}
close $fh;
my @top = (sort { $freq{$b} <=> $freq{$a} || $a cmp $b } keys %freq)[0 .. 9];
printf "lines=%d chars=%d unique=%d top=%s\n", $lines, $chars, scalar(keys %freq), join(',', @top);
