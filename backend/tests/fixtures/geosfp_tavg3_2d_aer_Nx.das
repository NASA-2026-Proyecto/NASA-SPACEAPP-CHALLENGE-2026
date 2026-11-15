Attributes {
    NC_GLOBAL {
        String title "GEOS5 FP 2d time-averaged primary aerosol diagnostics";
        String Conventions "COARDS", "GrADS";
        String dataType "Grid";
        String history "Sat Nov 14 17:21:37 EST 2026 : imported by GrADS Data Server 2.0";
        String extra_das_attribute "This is an example of metadata added using a supplementary DAS file. See testdata/extra.das for the source.";
    }
    lon {
        String grads_dim "x";
        String grads_mapping "linear";
        String grads_size "1152";
        String units "degrees_east";
        String long_name "longitude";
        Float64 minimum -180.00000000000;
        Float64 maximum 179.68750000000;
        Float32 resolution 0.3125;
    }
    lat {
        String grads_dim "y";
        String grads_mapping "linear";
        String grads_size "721";
        String units "degrees_north";
        String long_name "latitude";
        Float64 minimum -90.00000000000;
        Float64 maximum 90.00000000000;
        Float32 resolution 0.25;
    }
    time {
        String grads_dim "t";
        String grads_mapping "linear";
        String grads_size "2085";
        String grads_min "01:30z27feb2026";
        String grads_step "180mn";
        String units "days since 1-1-1 00:00:0.0";
        String long_name "time";
        String minimum "01:30z27feb2026";
        String maximum "13:30z14nov2026";
        Float32 resolution 0.125;
    }
    sscmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt column mass density ";
    }
    bcstscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc stratospheric aerosol optical thickness due to scattering ";
    }
    ocstexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc stratospheric aerosol optical thickness ";
    }
    nicmass25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate column mass density of particulate matter < 2.5 microns (pm2.5) ";
    }
    pm25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total reconstructed dry particulate matter < 2.5 microns (pm2.5) ";
    }
    bccmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol column mass density ";
    }
    dustexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust stratospheric aerosol optical thickness ";
    }
    nifluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate column u-wind mass flux ";
    }
    ssscat25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt aerosol optical depth due to scattering from particulate matter < 2.5 microns (pm2.5) ";
    }
    ocscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol optical depth due to scattering ";
    }
    suangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 angstrom parameter [470-870 nm] ";
    }
    ocfluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol column v-wind mass flux ";
    }
    niangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate angstrom parameter [470-870 nm] ";
    }
    so4smass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 surface mass concentration ";
    }
    sscmass25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt column mass density of particulate matter < 2.5 microns (pm2.5) ";
    }
    ocstscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc stratospheric aerosol optical thickness due to scattering ";
    }
    dustscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust stratospheric aerosol optical thickness due to scattering ";
    }
    ducmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust column mass density ";
    }
    dufluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust column u-wind mass flux ";
    }
    brstexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br stratospheric aerosol optical thickness ";
    }
    sustexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 stratospheric aerosol optical thickness ";
    }
    bcsmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol surface mass concentration ";
    }
    suscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 aerosol optical depth due to scattering ";
    }
    nh3smass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "ammonia surface mass concentration ";
    }
    ssfluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt column v-wind mass flux ";
    }
    bcfluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol column v-wind mass flux ";
    }
    nifluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate column v-wind mass flux ";
    }
    bcexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol optical depth ";
    }
    dmscmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dms column mass density ";
    }
    dufluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust column v-wind mass flux ";
    }
    niexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate aerosol optical depth ";
    }
    hno3cmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitric acid column mass density ";
    }
    ocfluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol column u-wind mass flux ";
    }
    duscat25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust aerosol optical depth due to scattering from particulate matter < 2.5 microns (pm2.5) ";
    }
    duexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust aerosol optical depth ";
    }
    bcstexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc stratospheric aerosol optical thickness ";
    }
    brstscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br stratospheric aerosol optical thickness due to scattering ";
    }
    ssfluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt column u-wind mass flux ";
    }
    dmssmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dms surface mass concentration ";
    }
    so2cmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so2 column mass density ";
    }
    bcfluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol column u-wind mass flux ";
    }
    sssmass25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt surface mass concentration of particulate matter < 2.5 microns (pm2.5) ";
    }
    ssscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt aerosol optical depth due to scattering ";
    }
    brsmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol surface mass concentration ";
    }
    so4cmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 column mass density ";
    }
    nh4smass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "ammonium surface mass concentration ";
    }
    taitime {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "taitime ";
    }
    nh4cmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "ammonium column mass density ";
    }
    brfluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol column v-wind mass flux ";
    }
    niexttfm {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate aerosol optical depth from particulate matter < 1 micron (pm1.0) ";
    }
    sustscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 stratospheric aerosol optical depth due to scattering ";
    }
    suexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 aerosol optical depth ";
    }
    duextt25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust aerosol optical depth from particulate matter < 2.5 microns (pm2.5) ";
    }
    duangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust angstrom parameter [470-870 nm] ";
    }
    pm {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total reconstructed dry particulate matter ";
    }
    brscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol optical depth due to scattering ";
    }
    sufluxv {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 column v-wind mass flux ";
    }
    ssangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt angstrom parameter [470-870 nm] ";
    }
    totexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total aerosol optical depth at 550 nm ";
    }
    totstexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total stratospheric aerosol optical thickness at 550 nm ";
    }
    ssstexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt stratospheric aerosol optical thickness ";
    }
    ssextt25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt aerosol optical depth from particulate matter < 2.5 microns (pm2.5) ";
    }
    dusmass25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust surface mass concentration of particulate matter < 2.5 microns (pm 2.5) ";
    }
    nicmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate column mass density ";
    }
    brexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol optical depth ";
    }
    ssexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt aerosol optical depth ";
    }
    nismass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate surface mass concentration ";
    }
    ssstscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt stratospheric aerosol optical thickness due to scattering ";
    }
    dusmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust surface mass concentration ";
    }
    niscatfm {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate aerosol optical depth due to scattering from particulate matter < 1 micron (pm1.0) ";
    }
    sssmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "sea salt surface mass concentration ";
    }
    nismass25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate surface mass concentration of particulate matter < 2.5 microns (pm2.5) ";
    }
    brcmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol column mass density ";
    }
    totstscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total stratospheric aerosol optical thickness at 550 nm due to scattering ";
    }
    hno3smass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitric acid surface mass concentration ";
    }
    totscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total aerosol optical depth at 550 nm due to scattering ";
    }
    occmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol column mass density ";
    }
    bcscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol optical depth due to scattering ";
    }
    ocangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol angstrom parameter [470-870 nm] ";
    }
    brfluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol column u-wind mass flux ";
    }
    duscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust aerosol optical depth due to scattering ";
    }
    brangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "br aerosol angstrom parameter [470-870 nm] ";
    }
    bcangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "bc aerosol angstrom parameter [470-870 nm] ";
    }
    totangstr {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "total aerosol angstrom parameter [470-870 nm] ";
    }
    sufluxu {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so4 column u-wind mass flux ";
    }
    ocsmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol surface mass concentration ";
    }
    ocexttau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "oc aerosol optical depth ";
    }
    so2smass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "so2 surface mass concentration ";
    }
    niscatau {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "nitrate aerosol optical depth due to scattering ";
    }
    ducmass25 {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "dust column mass density of particulate matter < 2.5 microns (pm 2.5) ";
    }
    nh3cmass {
        Float32 _FillValue 1.0E15;
        Float32 missing_value 1.0E15;
        String long_name "ammonia column mass density ";
    }
}
