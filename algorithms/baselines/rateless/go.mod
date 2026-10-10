module figure2_riblt_engine

go 1.21

require (
	github.com/dchest/siphash v1.2.3
	github.com/yangl1996/riblt v0.0.0
)


replace github.com/yangl1996/riblt => ../../dependencies/riblt
replace github.com/dchest/siphash => ../../dependencies/siphash
