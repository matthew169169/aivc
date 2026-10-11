classdef ShewanellaGeckoAdapter < ModelAdapter
    methods
        function obj = ShewanellaGeckoAdapter()
            obj.params.path = fileparts(mfilename('fullpath'));
            obj.params.convGEM = fullfile(obj.params.path,'model.xml');
            obj.params.sigma = 0.5;
            obj.params.Ptot = 0.48;
            obj.params.f = 0.5;
            obj.params.gR_exp = 0.15;
            obj.params.c_UptakeExp = [];
            obj.params.org_name = 'shewanella oneidensis';
            obj.params.complex.taxonomicID = 211586.0;
            obj.params.kegg.ID = 'son';
            obj.params.kegg.geneID = 'kegg';
            obj.params.uniprot.type = 'proteome';
            obj.params.uniprot.ID = 'UP000008186';
            obj.params.uniprot.geneIDfield = 'gene_oln';
            obj.params.uniprot.reviewed = false;
            obj.params.c_source = 'EX_cpd00159_e0';
            obj.params.bioRxn = 'bio1';
            obj.params.enzyme_comp = 'c0';
        end

        function [spont,spontRxnNames] = getSpontaneousReactions(obj,model)

            if isfield(model,'rxnNames')
                spont = contains(lower(model.rxnNames),'spontaneous');
                spontRxnNames = model.rxnNames(spont);
            else
                spont = false(size(model.rxns));
                spontRxnNames = {};
            end
        end
    end
end
